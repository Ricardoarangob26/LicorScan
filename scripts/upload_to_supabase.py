#!/usr/bin/env python3
"""Upload catalog to Supabase.

Usage:
  python scripts/upload_to_supabase.py --catalog frontend/catalog-data.js

Requires environment variables in a .env file:
  SUPABASE_URL
  SUPABASE_KEY

This script reads the JS file produced by the front-end build, extracts
the `window.__CATALOG__` JSON and upserts rows into a `products` table.
It uses the Supabase REST API directly, so it works with the newer API
keys exposed in the dashboard.

If SUPABASE_DB_URL is set (a direct Postgres connection string) and
--via-db is passed, it upserts straight over Postgres instead. Useful
when RLS only grants public SELECT on `products` and no service_role
key is available for REST writes.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

def extract_catalog_from_js(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r"window\.__CATALOG__\s*=\s*(\{.*\})\s*;\s*$", text, flags=re.S | re.M)
    if not m:
        raise ValueError(f"No catalog JSON found in {path}")
    return json.loads(m.group(1))


def normalize_product(p: dict) -> dict:
    return {
        "id": p.get("id") or f"{p.get('store')}-{p.get('sku') or p.get('id')}",
        "store": p.get("store"),
        "store_name": p.get("store_name"),
        "title": p.get("title"),
        "price": p.get("price"),
        "img": p.get("img"),
        "url": p.get("url"),
        "category": p.get("category"),
        "pricing_context": p.get("pricing_context"),
        "history": p.get("history"),
        "raw": p,
    }


def ensure_base_url(url: str) -> str:
    return url.rstrip("/")


def rest_upsert_batch(base_url: str, api_key: str, table: str, batch: list[dict]) -> tuple[int, str]:
    endpoint = f"{ensure_base_url(base_url)}/rest/v1/{table}?on_conflict=id"
    payload = json.dumps(batch, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase REST error {exc.code}: {body}") from exc


def db_upsert_batch(dsn: str, table: str, batch: list[dict]) -> None:
    import psycopg2
    import psycopg2.extras

    columns = ["id", "store", "store_name", "title", "price", "img", "url", "category", "pricing_context", "history", "raw"]
    json_cols = {"pricing_context", "history", "raw"}
    rows = [
        tuple(
            psycopg2.extras.Json(rec[c]) if c in json_cols else rec[c]
            for c in columns
        )
        for rec in batch
    ]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
    query = (
        f"insert into {table} ({', '.join(columns)}) values %s "
        f"on conflict (id) do update set {update_clause}"
    )
    conn = psycopg2.connect(dsn, connect_timeout=15)
    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, query, rows)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="frontend/catalog-data.js")
    parser.add_argument("--table", default="products")
    parser.add_argument("--batch", type=int, default=200, help="Batch size for upsert")
    parser.add_argument("--via-db", action="store_true", help="Upsert over direct Postgres connection (SUPABASE_DB_URL) instead of REST")
    args = parser.parse_args()

    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        raise SystemExit(f"Catalog file not found: {catalog_path}")

    catalog = extract_catalog_from_js(catalog_path)
    products = catalog.get("products") or []
    print(f"Found {len(products)} products in catalog")

    records = [normalize_product(p) for p in products]

    if args.via_db:
        dsn = os.environ.get("SUPABASE_DB_URL")
        if not dsn:
            raise SystemExit("Missing SUPABASE_DB_URL in environment (.env)")
        for i in range(0, len(records), args.batch):
            batch = records[i : i + args.batch]
            print(f"Upserting batch {i}..{i+len(batch)-1} (db)")
            db_upsert_batch(dsn, args.table, batch)
    else:
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise SystemExit("Missing SUPABASE_URL or SUPABASE_KEY in environment (.env)")
        for i in range(0, len(records), args.batch):
            batch = records[i : i + args.batch]
            print(f"Upserting batch {i}..{i+len(batch)-1}")
            status, body = rest_upsert_batch(SUPABASE_URL, SUPABASE_KEY, args.table, batch)
            if status not in (200, 201):
                raise RuntimeError(f"Unexpected Supabase status {status}: {body}")
            if i == 0:
                print(f"First batch response status={status}")

    print("Done.")


if __name__ == "__main__":
    main()
