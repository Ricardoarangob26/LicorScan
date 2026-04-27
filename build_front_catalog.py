from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from scraper.pricing_context import build_pricing_context, load_real_cartagena_home_matches


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
FRONTEND_DIR = BASE_DIR / "frontend"
HISTORY_FILES_PER_STORE = int(os.getenv("FRONT_HISTORY_FILES", "8"))


@dataclass(frozen=True)
class FrontProduct:
    id: int
    title: str
    store: str
    store_name: str
    category: str
    price: float
    img: str | None
    url: str
    scraped_date: str | None
    history: list[dict[str, object]]
    pricing_context: dict[str, object]


def _jsonl_by_store() -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in RAW_DIR.glob("*.jsonl"):
        stem = path.stem
        if "_" not in stem:
            continue
        store = stem.split("_", 1)[0]
        grouped[store].append(path)

    for store in grouped:
        grouped[store].sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return grouped


def _title_case_category(value: str | None) -> str:
    if not value:
        return "Otros"
    normalized = value.strip().replace("_", " ").replace("-", " ")
    if not normalized:
        return "Otros"
    return " ".join(part.capitalize() for part in normalized.split())


def _extract_file_timestamp(file_path: Path) -> str:
    # Espera formato: tienda_YYYYmmddTHHMMSSZ.jsonl
    raw = file_path.stem.split("_", 1)[1]
    stamp = datetime.strptime(raw, "%Y%m%dT%H%M%SZ")
    return stamp.date().isoformat()


def _build_history_map(files: list[Path]) -> dict[tuple[str, str], list[dict[str, object]]]:
    history_by_product: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)

    for path in sorted(files, key=lambda p: p.stat().st_mtime):
        day = _extract_file_timestamp(path)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue

                item = json.loads(line)
                price = item.get("price_cop")
                url = (item.get("url") or "").strip()
                name = (item.get("name") or "").strip()
                if not name or price is None:
                    continue

                key = (url, name)
                # Si hay varios registros mismo dia, guardamos el ultimo visto.
                history_by_product[key][day] = float(price)

    out: dict[tuple[str, str], list[dict[str, object]]] = {}
    for key, by_day in history_by_product.items():
        points = [{"date": day, "price": by_day[day]} for day in sorted(by_day)]
        out[key] = points
    return out


def _load_products_from_file(
    path: Path,
    start_id: int,
    history_map: dict[tuple[str, str], list[dict[str, object]]],
    real_cartagena_matches: list[dict[str, object]],
) -> list[FrontProduct]:
    rows: list[FrontProduct] = []
    next_id = start_id
    seen_urls: set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            item = json.loads(line)
            price = item.get("price_cop")
            url = (item.get("url") or "").strip()
            name = (item.get("name") or "").strip()
            if not name or price is None or not url:
                continue
            if url in seen_urls:
                continue

            seen_urls.add(url)
            history_key = (url, name)
            history = history_map.get(history_key, [])
            rows.append(
                FrontProduct(
                    id=next_id,
                    title=name,
                    store=(item.get("store") or "").strip(),
                    store_name=(item.get("store_name") or item.get("store") or "").strip(),
                    category=_title_case_category(item.get("category")),
                    price=float(price),
                    img=item.get("image_url"),
                    url=url,
                    scraped_date=item.get("scraped_date"),
                    history=history,
                    pricing_context=build_pricing_context(history, home_matches=real_cartagena_matches),
                )
            )
            next_id += 1

    return rows


def build_catalog() -> dict[str, object]:
    files_by_store = _jsonl_by_store()
    products: list[FrontProduct] = []
    next_id = 1
    latest_files: dict[str, Path] = {}
    real_cartagena_matches = load_real_cartagena_home_matches()

    for store in sorted(files_by_store):
        store_files = files_by_store[store]
        latest_file = store_files[0]
        latest_files[store] = latest_file
        history_files = store_files[:HISTORY_FILES_PER_STORE]
        history_map = _build_history_map(history_files)

        rows = _load_products_from_file(latest_file, next_id, history_map, real_cartagena_matches)
        products.extend(rows)
        next_id += len(rows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": {store: str(path) for store, path in latest_files.items()},
        "product_count": len(products),
        "products": [row.__dict__ for row in products],
    }
    return payload


def write_catalog(payload: dict[str, object]) -> Path:
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    out_file = FRONTEND_DIR / "catalog-data.js"
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out_file.write_text(f"window.__CATALOG__ = {serialized};\n", encoding="utf-8")
    return out_file


def main() -> None:
    payload = build_catalog()
    out_file = write_catalog(payload)
    print(f"Catalog file: {out_file}")
    print(f"Products: {payload['product_count']}")


if __name__ == "__main__":
    main()
