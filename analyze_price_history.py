"""Analiza el historial de precios a partir de los JSONL recientes.

Uso:
    python analyze_price_history.py --store exito
    python analyze_price_history.py --store exito --files 3 --top 20

La utilidad agrupa por producto usando la URL cuando está disponible,
y calcula mínimo, máximo, promedio y variación entre la primera y la
última fecha observada.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
DERIVED_DIR = BASE_DIR / "data" / "derived"


@dataclass(frozen=True)
class PricePoint:
    scraped_date: str
    price_cop: float
    name: str
    category: str
    url: str
    store_name: str | None


@dataclass(frozen=True)
class ProductSeries:
    key: str
    name: str
    category: str
    store_name: str
    url: str
    first_date: str
    last_date: str
    count: int
    min_price: float
    max_price: float
    avg_price: float
    first_price: float
    last_price: float
    delta_cop: float
    delta_pct: float | None
    history: list[dict[str, object]]
    daily_series: list[dict[str, object]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analiza histórico de precios desde JSONL")
    parser.add_argument("--store", default="exito", help="Prefijo de tienda a analizar")
    parser.add_argument("--files", type=int, default=3, help="Cantidad de JSONL recientes a leer")
    parser.add_argument("--top", type=int, default=20, help="Cantidad de productos a mostrar")
    parser.add_argument(
        "--export-json",
        default=str(DERIVED_DIR / "price_history.json"),
        help="Ruta del JSON para front-end",
    )
    parser.add_argument(
        "--export-csv",
        default=str(DERIVED_DIR / "price_history_summary.csv"),
        help="Ruta del CSV resumen para front-end",
    )
    return parser.parse_args()


def load_points(store: str, file_limit: int) -> list[PricePoint]:
    files = sorted(
        RAW_DIR.glob(f"{store}_*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:file_limit]

    points: list[PricePoint] = []
    for file_path in files:
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                price = item.get("price_cop")
                if price is None:
                    continue
                scraped_date = item.get("scraped_date") or str(item.get("scraped_at", ""))[:10]
                points.append(
                    PricePoint(
                        scraped_date=scraped_date,
                        price_cop=float(price),
                        name=item.get("name") or "",
                        category=item.get("category") or "",
                        url=item.get("url") or "",
                        store_name=item.get("store_name"),
                    )
                )
    return points


def build_series(points: list[PricePoint]) -> dict[str, list[PricePoint]]:
    series: dict[str, list[PricePoint]] = defaultdict(list)
    for point in points:
        key = point.url or point.name
        series[key].append(point)
    for key in series:
        series[key].sort(key=lambda point: (point.scraped_date, point.price_cop))
    return series


def build_daily_series(history: list[PricePoint]) -> list[dict[str, object]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for point in history:
        grouped[point.scraped_date].append(point.price_cop)

    daily_points = []
    for scraped_date in sorted(grouped):
        values = grouped[scraped_date]
        daily_points.append(
            {
                "date": scraped_date,
                "price_cop": values[-1],
                "avg_price_cop": mean(values),
                "min_price_cop": min(values),
                "max_price_cop": max(values),
                "samples": len(values),
            }
        )
    return daily_points


def build_product_series(key: str, history: list[PricePoint]) -> ProductSeries:
    prices = [point.price_cop for point in history]
    first = history[0]
    last = history[-1]
    delta = last.price_cop - first.price_cop
    delta_pct = None if first.price_cop == 0 else (delta / first.price_cop) * 100
    return ProductSeries(
        key=key,
        name=last.name or first.name,
        category=last.category or first.category,
        store_name=last.store_name or first.store_name or "",
        url=last.url or first.url,
        first_date=first.scraped_date,
        last_date=last.scraped_date,
        count=len(prices),
        min_price=min(prices),
        max_price=max(prices),
        avg_price=mean(prices),
        first_price=first.price_cop,
        last_price=last.price_cop,
        delta_cop=delta,
        delta_pct=delta_pct,
        history=[
            {
                "date": point.scraped_date,
                "price_cop": point.price_cop,
                "name": point.name,
                "category": point.category,
                "url": point.url,
                "store_name": point.store_name,
            }
            for point in history
        ],
        daily_series=build_daily_series(history),
    )


def write_json_export(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_csv_summary(path: Path, rows: list[ProductSeries]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "key",
                "name",
                "category",
                "store_name",
                "url",
                "count",
                "min_price",
                "max_price",
                "avg_price",
                "first_date",
                "last_date",
                "first_price",
                "last_price",
                "delta_cop",
                "delta_pct",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "key": row.key,
                    "name": row.name,
                    "category": row.category,
                    "store_name": row.store_name,
                    "url": row.url,
                    "count": row.count,
                    "min_price": f"{row.min_price:.2f}",
                    "max_price": f"{row.max_price:.2f}",
                    "avg_price": f"{row.avg_price:.2f}",
                    "first_date": row.first_date,
                    "last_date": row.last_date,
                    "first_price": f"{row.first_price:.2f}",
                    "last_price": f"{row.last_price:.2f}",
                    "delta_cop": f"{row.delta_cop:.2f}",
                    "delta_pct": "" if row.delta_pct is None else f"{row.delta_pct:.4f}",
                }
            )


def main() -> None:
    args = parse_args()
    points = load_points(args.store, args.files)
    if not points:
        print(f"No se encontraron datos para '{args.store}' en {RAW_DIR}")
        return

    series = build_series(points)
    ranked: list[ProductSeries] = []
    for key, history in series.items():
        ranked.append(build_product_series(key, history))

    ranked.sort(key=lambda item: (item.last_date, item.count, item.name), reverse=True)

    export_payload = {
        "store": args.store,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [str(path) for path in sorted(RAW_DIR.glob(f"{args.store}_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[: args.files]],
        "files_analyzed": min(args.files, len(list(RAW_DIR.glob(f"{args.store}_*.jsonl")))),
        "records_loaded": len(points),
        "product_count": len(ranked),
        "products": [
            {
                "key": item.key,
                "name": item.name,
                "category": item.category,
                "store_name": item.store_name,
                "url": item.url,
                "count": item.count,
                "min_price_cop": item.min_price,
                "max_price_cop": item.max_price,
                "avg_price_cop": item.avg_price,
                "first_date": item.first_date,
                "last_date": item.last_date,
                "first_price_cop": item.first_price,
                "last_price_cop": item.last_price,
                "delta_cop": item.delta_cop,
                "delta_pct": item.delta_pct,
                "history": item.history,
                "daily_series": item.daily_series,
            }
            for item in ranked
        ],
    }

    export_json = Path(args.export_json)
    export_csv = Path(args.export_csv)
    write_json_export(export_json, export_payload)
    write_csv_summary(export_csv, ranked)

    print(f"Archivos analizados: {min(args.files, len(list(RAW_DIR.glob(f'{args.store}_*.jsonl'))))}")
    print(f"Productos con historial: {len(ranked)}")
    print(f"JSON frontend: {export_json}")
    print(f"CSV resumen: {export_csv}")
    print()

    for item in ranked[: args.top]:
        print(
            f"{item.name} | {item.category} | {item.store_name} | "
            f"n={item.count} | min={item.min_price:.2f} | max={item.max_price:.2f} | avg={item.avg_price:.2f} | "
            f"{item.first_date} -> {item.last_date} | {item.delta_cop:+.2f} COP"
        )


if __name__ == "__main__":
    main()