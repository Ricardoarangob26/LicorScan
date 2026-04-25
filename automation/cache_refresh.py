from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

from build_front_catalog import build_catalog, write_catalog


BASE_DIR = Path(__file__).resolve().parent.parent
STATUS_DIR = BASE_DIR / "data" / "cache"
STATUS_FILE = STATUS_DIR / "cache_status.json"


def parse_args() -> argparse.Namespace:
    default_source = os.getenv("CACHE_SOURCE", "raw_jsonl")
    parser = argparse.ArgumentParser(description="Job de refresco de cache sin scraping")
    parser.add_argument(
        "--source",
        choices=["raw_jsonl", "db_json"],
        default=default_source,
        help="Origen de datos para refrescar cache",
    )
    parser.add_argument(
        "--db-json-path",
        default="",
        help="Ruta a export JSON desde BD (solo aplica con --source db_json)",
    )
    parser.add_argument("--cache-ttl-minutes", type=int, default=30, help="TTL logico del cache")
    return parser.parse_args()


def _normalize_db_products(payload: object) -> list[dict[str, object]]:
    rows = payload.get("products", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("El JSON de BD debe ser una lista o un objeto con clave 'products'.")

    normalized: list[dict[str, object]] = []
    for idx, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue

        title = (item.get("title") or item.get("name") or "").strip()
        store = (item.get("store") or "").strip()
        if not title or not store:
            continue

        price_raw = item.get("price")
        if price_raw is None:
            price_raw = item.get("price_cop")
        if price_raw is None:
            continue

        normalized.append(
            {
                "id": int(item.get("id") or idx),
                "title": title,
                "store": store,
                "store_name": (item.get("store_name") or store).strip(),
                "category": (item.get("category") or "Otros").strip(),
                "price": float(price_raw),
                "img": item.get("img") or item.get("image_url") or item.get("image"),
                "url": (item.get("url") or "").strip(),
                "scraped_date": item.get("scraped_date") or item.get("updated_at"),
            }
        )

    return normalized


def _build_payload_from_db_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"No existe export JSON de BD: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    products = _normalize_db_products(payload)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "db_json",
        "source_files": {"db_json": str(path)},
        "product_count": len(products),
        "products": products,
    }


def write_cache_status(source: str, ttl_minutes: int, product_count: int) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    next_refresh_at = now + timedelta(minutes=ttl_minutes)

    existing: dict[str, object] = {}
    if STATUS_FILE.exists():
        try:
            existing = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    payload = {
        "updated_at": now.isoformat(),
        "cache": {
            "path": "frontend/catalog-data.js",
            "source": source,
            "ttl_minutes": ttl_minutes,
            "next_refresh_at": next_refresh_at.isoformat(),
            "refreshed_this_cycle": True,
            "mode": "cache_only",
            "product_count": product_count,
        },
        "jobs": existing.get("jobs", []),
    }
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()

    logger.info(f"[cache] Iniciando refresco de cache. source={args.source}")

    if args.source == "raw_jsonl":
        payload = build_catalog()
    else:
        if not args.db_json_path:
            raise ValueError("Con source=db_json debes enviar --db-json-path")
        payload = _build_payload_from_db_json(Path(args.db_json_path))

    out_file = write_catalog(payload)
    write_cache_status(args.source, args.cache_ttl_minutes, int(payload.get("product_count", 0)))

    logger.success(f"[cache] Refresco OK -> {out_file}")
    logger.info(f"[cache] Productos en cache: {payload.get('product_count', 0)}")


if __name__ == "__main__":
    main()
