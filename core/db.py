"""Acceso a datos. SQL plano sobre psycopg2, sin ORM.

Se conecta con SUPABASE_DB_URL (conexión directa a Postgres), que no
está sujeta a RLS: las políticas dejan lectura pública y la escritura
pasa solo por aquí.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from core.models import NormalizedProduct, StoreConfig
from core.normalize import normalize_text, slugify

BASE_DIR = Path(__file__).resolve().parent.parent


def get_dsn() -> str:
    load_dotenv(BASE_DIR / ".env")
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        raise SystemExit("Falta SUPABASE_DB_URL en el .env")
    return dsn


@contextmanager
def connect(retries: int = 3):
    """Conexión con reintentos.

    Importante: no sostener una conexión abierta durante toda una
    ingesta. Entre lote y lote hay peticiones HTTP con pausas, y una
    conexión ociosa tantos minutos termina cortada por el pooler
    ('connection already closed'). Se abre por lote y se cierra.
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(get_dsn(), connect_timeout=20)
            break
        except psycopg2.Error as exc:
            last_error = exc
            if attempt == retries:
                raise
            time.sleep(2 * attempt)
    else:  # pragma: no cover
        raise last_error  # type: ignore[misc]

    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


class Repository:
    """Operaciones de escritura del pipeline de ingesta."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self._brand_cache: dict[str, int] = {}
        self._category_cache: dict[str, int] = {}

    # ---- Tiendas ----

    def upsert_store(self, config: StoreConfig) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into stores (country_code, slug, name, website, platform, config)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (slug) do update set
                    name = excluded.name,
                    website = excluded.website,
                    platform = excluded.platform,
                    config = excluded.config
                returning id
                """,
                (
                    config.country_code,
                    config.slug,
                    config.name,
                    config.base_url,
                    config.platform,
                    psycopg2.extras.Json(
                        {
                            "base_url": config.base_url,
                            "sales_channel": config.sales_channel,
                            "category_ids": config.category_ids,
                            "delay_seconds": config.delay_seconds,
                        }
                    ),
                ),
            )
            return cur.fetchone()[0]

    def get_store_id(self, slug: str) -> int | None:
        with self.conn.cursor() as cur:
            cur.execute("select id from stores where slug = %s", (slug,))
            row = cur.fetchone()
            return row[0] if row else None

    # ---- Marcas y categorías ----

    def get_or_create_brand(self, name: str | None) -> int | None:
        if not name or not name.strip():
            return None
        slug = slugify(name)
        if slug in self._brand_cache:
            return self._brand_cache[slug]
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into brands (slug, name) values (%s, %s)
                on conflict (slug) do update set name = excluded.name
                returning id
                """,
                (slug, name.strip()),
            )
            brand_id = cur.fetchone()[0]
        self._brand_cache[slug] = brand_id
        return brand_id

    def get_or_create_category(self, path: str | None) -> int | None:
        """Crea la cadena de categorías a partir de la ruta de la tienda.

        Cada tienda tiene su propio árbol y no coinciden entre sí; el
        mapeo a un árbol canónico único es un problema aparte, así que
        por ahora se conserva la jerarquía tal como viene.
        """
        if not path:
            return None
        segments = [seg.strip() for seg in path.split("/") if seg.strip()]
        if not segments:
            return None

        parent_id: int | None = None
        accumulated: list[str] = []
        for segment in segments:
            accumulated.append(slugify(segment))
            slug = "/".join(accumulated)
            cached = self._category_cache.get(slug)
            if cached is not None:
                parent_id = cached
                continue
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    insert into categories (parent_id, slug, name) values (%s, %s, %s)
                    on conflict (slug) do update set name = excluded.name
                    returning id
                    """,
                    (parent_id, slug, segment),
                )
                parent_id = cur.fetchone()[0]
            self._category_cache[slug] = parent_id
        return parent_id

    # ---- Corridas ----

    def start_run(self, store_id: int, adapter: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                "insert into scrape_runs (store_id, adapter) values (%s, %s) returning id",
                (store_id, adapter),
            )
            return cur.fetchone()[0]

    def finish_run(self, run_id: int, status: str, **counts: Any) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                update scrape_runs set
                    finished_at = now(), status = %s,
                    products_found = %s, products_new = %s,
                    prices_written = %s, errors = %s, notes = %s
                where id = %s
                """,
                (
                    status,
                    counts.get("products_found", 0),
                    counts.get("products_new", 0),
                    counts.get("prices_written", 0),
                    counts.get("errors", 0),
                    counts.get("notes"),
                    run_id,
                ),
            )

    # ---- Fichas de tienda ----

    def upsert_store_product(self, store_id: int, product: NormalizedProduct) -> tuple[int, bool]:
        """Devuelve (id, es_nuevo)."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into store_products (
                    store_id, sku, store_product_id, title, normalized_title,
                    url, image_url, store_category_path, barcode, raw, last_seen_at
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                on conflict (store_id, sku) do update set
                    title = excluded.title,
                    normalized_title = excluded.normalized_title,
                    url = excluded.url,
                    image_url = coalesce(excluded.image_url, store_products.image_url),
                    store_category_path = excluded.store_category_path,
                    barcode = coalesce(excluded.barcode, store_products.barcode),
                    raw = excluded.raw,
                    last_seen_at = now()
                returning id, (xmax = 0) as inserted
                """,
                (
                    store_id,
                    product.sku,
                    product.store_product_id,
                    product.title,
                    product.normalized_title or normalize_text(product.title),
                    product.url,
                    product.image_url,
                    product.category_path,
                    product.barcode,
                    psycopg2.extras.Json(product.raw or {}),
                ),
            )
            row = cur.fetchone()
            return row[0], row[1]

    def link_product(self, store_product_id: int, product_id: int | None,
                     method: str | None, confidence: float | None, needs_review: bool) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                update store_products
                set product_id = %s, match_method = %s,
                    match_confidence = %s, needs_review = %s
                where id = %s
                """,
                (product_id, method, confidence, needs_review, store_product_id),
            )

    # ---- Precios (append-only) ----

    def insert_price(self, store_product_id: int, product: NormalizedProduct, run_id: int | None) -> None:
        price = product.price
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into prices (
                    store_product_id, price, list_price, currency,
                    available, teasers, scrape_run_id
                ) values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    store_product_id,
                    price.price,
                    price.list_price,
                    price.currency,
                    price.available,
                    psycopg2.extras.Json(price.teasers or []),
                    run_id,
                ),
            )
