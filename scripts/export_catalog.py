#!/usr/bin/env python3
"""Exporta el catálogo desde la base normalizada al frontend actual.

    py scripts/export_catalog.py              # escribe catalog-data.js y sube a `products`
    py scripts/export_catalog.py --no-upload  # solo el archivo local

Puente entre lo nuevo y lo viejo: el frontend todavía lee la tabla
`products` heredada, pero los datos ya no salen de los JSONL del scraper
por DOM sino de la base normalizada que llena el adaptador VTEX.

Lo que esto desbloquea: el precio de lista (`list_price`) existe ahora
para las cuatro tiendas, no solo para Olímpica, así que el indicador de
promoción del frontend funciona en todo el catálogo. Y el historial deja
de recalcularse desde archivos rotados: sale de la tabla `prices`, que
es append-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras

BASE_DIR = Path(__file__).resolve().parent.parent
# El script se invoca como `py scripts/export_catalog.py`, así que la
# raíz del repo no está en sys.path por defecto.
sys.path.insert(0, str(BASE_DIR))

from core.db import connect  # noqa: E402
from scraper.pricing_context import (  # noqa: E402
    build_pricing_context,
    load_real_cartagena_home_matches,
)

FRONTEND_DIR = BASE_DIR / "frontend"

# Cuántos días de historial mandar al frontend por producto.
HISTORY_DAYS = 30


def stable_id(store_slug: str, url: str) -> str:
    """Mismo esquema que usa el catálogo actual, para no romper enlaces."""
    return f"{store_slug}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}"


def fetch_catalog(conn) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select
                sp.id as store_product_id,
                s.slug as store, s.name as store_name,
                coalesce(cp.name, sp.title) as title,
                pr.price, pr.list_price, pr.currency, pr.available,
                coalesce(sp.image_url, cp.image_url) as img,
                sp.url,
                coalesce(cat.name, split_part(sp.store_category_path, '/', 1), 'Otros') as category,
                cp.barcode, cp.quantity, cp.unit,
                b.name as brand,
                pr.captured_at
            from store_products sp
            join stores s on s.id = sp.store_id
            join current_prices pr on pr.store_product_id = sp.id
            left join catalog_products cp on cp.id = sp.product_id
            left join categories cat on cat.id = cp.category_id
            left join brands b on b.id = cp.brand_id
            where pr.price > 0
            order by s.slug, cp.name
            """
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_history(conn) -> dict[int, list[dict]]:
    """Historial por ficha de tienda, un punto por día.

    Antes esto se reconstruía leyendo los últimos JSONL del disco, que el
    propio scraper rotaba; ahora sale de la tabla de precios.
    """
    history: dict[int, dict[str, float]] = defaultdict(dict)
    with conn.cursor() as cur:
        cur.execute(
            """
            select store_product_id, date_trunc('day', captured_at)::date as day,
                   (array_agg(price order by captured_at desc))[1] as price
            from prices
            where captured_at >= now() - interval '%s days'
            group by store_product_id, day
            order by store_product_id, day
            """,
            (HISTORY_DAYS,),
        )
        for sp_id, day, price in cur.fetchall():
            history[sp_id][day.isoformat()] = float(price)

    return {
        sp_id: [{"date": d, "price": p} for d, p in sorted(by_day.items())]
        for sp_id, by_day in history.items()
    }


def build_products(rows: list[dict], history: dict[int, list[dict]]) -> list[dict]:
    matches = load_real_cartagena_home_matches()
    products = []

    for row in rows:
        price = float(row["price"])
        list_price = float(row["list_price"]) if row["list_price"] is not None else None
        # Defensivo: un precio de lista que no supere al de venta no es promoción.
        if list_price is not None and list_price <= price:
            list_price = None

        points = history.get(row["store_product_id"], [])
        products.append({
            "id": stable_id(row["store"], row["url"]),
            "title": row["title"],
            "store": row["store"],
            "store_name": row["store_name"],
            "category": row["category"],
            "price": price,
            "list_price": list_price,
            "img": row["img"],
            "url": row["url"],
            "barcode": row["barcode"],
            "brand": row["brand"],
            "scraped_date": row["captured_at"].date().isoformat(),
            "history": points,
            "pricing_context": build_pricing_context(
                points, home_matches=matches,
                current_price=price, list_price=list_price,
            ),
        })
    return products


def write_catalog(products: list[dict]) -> Path:
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "normalized_db",
        "product_count": len(products),
        "products": products,
    }
    out = FRONTEND_DIR / "catalog-data.js"
    out.write_text(
        f"window.__CATALOG__ = {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))};\n",
        encoding="utf-8",
    )
    return out


def upload_legacy(conn, products: list[dict], batch_size: int = 200) -> int:
    """Sube a la tabla `products` heredada, que es la que lee el frontend."""
    columns = ["id", "store", "store_name", "title", "price", "list_price",
               "img", "url", "category", "pricing_context", "history", "raw"]
    update = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
    query = (
        f"insert into products ({', '.join(columns)}) values %s "
        f"on conflict (id) do update set {update}"
    )

    rows = [
        (
            p["id"], p["store"], p["store_name"], p["title"], p["price"], p["list_price"],
            p["img"], p["url"], p["category"],
            psycopg2.extras.Json(p["pricing_context"]),
            psycopg2.extras.Json(p["history"]),
            psycopg2.extras.Json({"barcode": p["barcode"], "brand": p["brand"]}),
        )
        for p in products
    ]

    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            psycopg2.extras.execute_values(cur, query, rows[i:i + batch_size])
            conn.commit()
            print(f"  subidos {min(i + batch_size, len(rows))}/{len(rows)}")

    # Retirar lo que ya no está en el catálogo, para no dejar huérfanos.
    with conn.cursor() as cur:
        cur.execute("delete from products where not (id = any(%s))", ([p["id"] for p in products],))
        removed = cur.rowcount
        conn.commit()
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Exportar catálogo desde la base normalizada")
    parser.add_argument("--no-upload", action="store_true", help="Solo escribir el archivo local")
    args = parser.parse_args()

    with connect() as conn:
        rows = fetch_catalog(conn)
        history = fetch_history(conn)
        products = build_products(rows, history)

        by_store: dict[str, int] = defaultdict(int)
        promos: dict[str, int] = defaultdict(int)
        for p in products:
            by_store[p["store"]] += 1
            if p["list_price"]:
                promos[p["store"]] += 1

        out = write_catalog(products)
        print(f"Catálogo: {out}")
        print(f"Productos: {len(products)}")
        for store in sorted(by_store):
            print(f"  {store:<10} {by_store[store]:>5} productos, {promos[store]:>4} en promoción")

        if not args.no_upload:
            print("\nSubiendo a la tabla `products`…")
            removed = upload_legacy(conn, products)
            print(f"  retirados {removed} productos que ya no están en el catálogo")

    print("Listo.")


if __name__ == "__main__":
    main()
