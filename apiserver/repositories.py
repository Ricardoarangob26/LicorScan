"""Consultas de lectura.

SQL plano y explícito, sin ORM. Todas las consultas son parametrizadas:
nunca se interpola entrada del usuario en la sentencia.
"""
from __future__ import annotations

from typing import Any

from apiserver.database import fetch_all, fetch_one, fetch_value

# El precio vigente por ficha de tienda sale de la vista `current_prices`,
# que toma la observación más reciente de la tabla append-only `prices`.
_PRODUCT_SELECT = """
    select
        cp.id, cp.name, cp.barcode, cp.quantity, cp.unit, cp.image_url,
        b.id as brand_id, b.slug as brand_slug, b.name as brand_name,
        c.id as category_id, c.slug as category_slug,
        c.name as category_name, c.parent_id as category_parent_id,
        count(distinct sp.store_id) as store_count,
        min(pr.price) as min_price,
        max(pr.price) as max_price
    from catalog_products cp
    join store_products sp on sp.product_id = cp.id
    join current_prices pr on pr.store_product_id = sp.id
    left join brands b on b.id = cp.brand_id
    left join categories c on c.id = cp.category_id
"""

_PRODUCT_GROUP = """
    group by cp.id, b.id, c.id
"""


def _shape_product(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "barcode": row.get("barcode"),
        "quantity": float(row["quantity"]) if row.get("quantity") is not None else None,
        "unit": row.get("unit"),
        "image_url": row.get("image_url"),
        "store_count": row.get("store_count") or 0,
        "min_price": float(row["min_price"]) if row.get("min_price") is not None else None,
        "max_price": float(row["max_price"]) if row.get("max_price") is not None else None,
        "brand": (
            {"id": row["brand_id"], "slug": row["brand_slug"], "name": row["brand_name"]}
            if row.get("brand_id")
            else None
        ),
        "category": (
            {
                "id": row["category_id"],
                "slug": row["category_slug"],
                "name": row["category_name"],
                "parent_id": row.get("category_parent_id"),
            }
            if row.get("category_id")
            else None
        ),
    }


def _shape_store(row: dict, prefix: str = "store_") -> dict:
    return {
        "id": row[f"{prefix}id"],
        "slug": row[f"{prefix}slug"],
        "name": row[f"{prefix}name"],
        "country_code": row.get(f"{prefix}country", "CO"),
        "website": row.get(f"{prefix}website"),
        "active": row.get(f"{prefix}active", True),
    }


# ---------------------------------------------------------------- tiendas

def list_stores(active_only: bool = True) -> list[dict]:
    where = "where active" if active_only else ""
    return fetch_all(
        f"""
        select id, slug, name, country_code, website, active
        from stores {where} order by name
        """
    )


def get_store(slug: str) -> dict | None:
    return fetch_one(
        """
        select id, slug, name, country_code, website, active
        from stores where slug = %s
        """,
        (slug,),
    )


# --------------------------------------------------------------- catálogo

def list_brands(limit: int = 200, offset: int = 0) -> tuple[list[dict], int]:
    rows = fetch_all(
        """
        select b.id, b.slug, b.name, count(distinct cp.id) as product_count
        from brands b
        join catalog_products cp on cp.brand_id = b.id
        group by b.id
        order by product_count desc, b.name
        limit %s offset %s
        """,
        (limit, offset),
    )
    total = fetch_value("select count(distinct brand_id) from catalog_products where brand_id is not null")
    return rows, int(total or 0)


def list_categories() -> list[dict]:
    return fetch_all(
        """
        select c.id, c.slug, c.name, c.parent_id, count(distinct cp.id) as product_count
        from categories c
        left join catalog_products cp on cp.category_id = c.id
        group by c.id
        order by c.name
        """
    )


# --------------------------------------------------------------- productos

def _build_filters(
    store: str | None,
    category: str | None,
    brand: str | None,
    min_price: float | None,
    max_price: float | None,
    barcode: str | None,
    multi_store: bool,
) -> tuple[str, list[Any], str]:
    """Devuelve (where, params, having)."""
    clauses: list[str] = []
    params: list[Any] = []

    if store:
        clauses.append("sp.store_id = (select id from stores where slug = %s)")
        params.append(store)
    if category:
        clauses.append("c.slug = %s")
        params.append(category)
    if brand:
        clauses.append("b.slug = %s")
        params.append(brand)
    if barcode:
        clauses.append("cp.barcode = %s")
        params.append(barcode)
    if min_price is not None:
        clauses.append("pr.price >= %s")
        params.append(min_price)
    if max_price is not None:
        clauses.append("pr.price <= %s")
        params.append(max_price)

    where = ("where " + " and ".join(clauses)) if clauses else ""
    having = "having count(distinct sp.store_id) > 1" if multi_store else ""
    return where, params, having


def list_products(
    limit: int = 50,
    offset: int = 0,
    store: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    barcode: str | None = None,
    multi_store: bool = False,
    sort: str = "name",
) -> tuple[list[dict], int]:
    where, params, having = _build_filters(
        store, category, brand, min_price, max_price, barcode, multi_store
    )

    order = {
        "name": "cp.name asc",
        "price_asc": "min_price asc",
        "price_desc": "min_price desc",
        "stores": "store_count desc, cp.name asc",
    }.get(sort, "cp.name asc")

    rows = fetch_all(
        f"{_PRODUCT_SELECT} {where} {_PRODUCT_GROUP} {having} order by {order} limit %s offset %s",
        (*params, limit, offset),
    )

    total = fetch_value(
        f"""
        select count(*) from (
            select cp.id
            from catalog_products cp
            join store_products sp on sp.product_id = cp.id
            join current_prices pr on pr.store_product_id = sp.id
            left join brands b on b.id = cp.brand_id
            left join categories c on c.id = cp.category_id
            {where} group by cp.id {having}
        ) t
        """,
        tuple(params),
    )
    return [_shape_product(r) for r in rows], int(total or 0)


def search_products(query: str, limit: int = 50, offset: int = 0,
                    store: str | None = None) -> tuple[list[dict], int]:
    """Búsqueda difusa por similitud de trigramas.

    Tolera diferencias de escritura entre tiendas, que es justo el
    problema: 'Whisky OLD PARR 12 años' vs 'WHISKY OLD PARR 12 AÑOS'.
    """
    from core.normalize import normalize_text

    needle = normalize_text(query)
    if not needle:
        return [], 0

    clauses = ["(cp.normalized_name %% %s or cp.normalized_name ilike %s)"]
    params: list[Any] = [needle, f"%{needle}%"]
    if store:
        clauses.append("sp.store_id = (select id from stores where slug = %s)")
        params.append(store)
    where = "where " + " and ".join(clauses)

    rows = fetch_all(
        f"""
        {_PRODUCT_SELECT} {where} {_PRODUCT_GROUP}
        order by similarity(cp.normalized_name, %s) desc, cp.name
        limit %s offset %s
        """,
        (*params, needle, limit, offset),
    )
    total = fetch_value(
        f"""
        select count(*) from (
            select cp.id
            from catalog_products cp
            join store_products sp on sp.product_id = cp.id
            join current_prices pr on pr.store_product_id = sp.id
            {where} group by cp.id
        ) t
        """,
        tuple(params),
    )
    return [_shape_product(r) for r in rows], int(total or 0)


def get_product(product_id: int) -> dict | None:
    row = fetch_one(
        f"{_PRODUCT_SELECT} where cp.id = %s {_PRODUCT_GROUP}",
        (product_id,),
    )
    return _shape_product(row) if row else None


def get_product_prices(product_id: int) -> list[dict]:
    rows = fetch_all(
        """
        select
            s.id as store_id, s.slug as store_slug, s.name as store_name,
            s.country_code as store_country, s.website as store_website,
            s.active as store_active,
            pr.price, pr.list_price, pr.currency, pr.available,
            pr.captured_at, sp.url
        from store_products sp
        join stores s on s.id = sp.store_id
        join current_prices pr on pr.store_product_id = sp.id
        where sp.product_id = %s
        order by pr.price asc
        """,
        (product_id,),
    )
    out = []
    for row in rows:
        price = float(row["price"])
        list_price = float(row["list_price"]) if row["list_price"] is not None else None
        discount_pct = None
        if list_price and list_price > price:
            discount_pct = round((list_price - price) / list_price * 100, 2)
        out.append({
            "store": _shape_store(row),
            "price": price,
            "list_price": list_price,
            "discount_pct": discount_pct,
            "currency": row["currency"],
            "available": row["available"],
            "url": row["url"],
            "updated_at": row["captured_at"],
        })
    return out


def get_price_history(product_id: int, store: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      limit: int = 1000) -> list[dict]:
    clauses = ["sp.product_id = %s"]
    params: list[Any] = [product_id]
    if store:
        clauses.append("s.slug = %s")
        params.append(store)
    if date_from:
        clauses.append("p.captured_at >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("p.captured_at <= %s")
        params.append(date_to)

    return fetch_all(
        f"""
        select s.slug as store_slug, p.price, p.list_price,
               p.available, p.captured_at
        from prices p
        join store_products sp on sp.id = p.store_product_id
        join stores s on s.id = sp.store_id
        where {' and '.join(clauses)}
        order by p.captured_at asc
        limit %s
        """,
        (*params, limit),
    )


# ------------------------------------------------------------ comparación

def get_prices_for_products(product_ids: list[int], stores: list[str] | None = None) -> list[dict]:
    """Precio vigente de varios productos en todas las tiendas, de una sola vez."""
    clauses = ["sp.product_id = any(%s)", "pr.available"]
    params: list[Any] = [product_ids]
    if stores:
        clauses.append("s.slug = any(%s)")
        params.append(stores)

    return fetch_all(
        f"""
        select
            sp.product_id, cp.name as product_name,
            s.id as store_id, s.slug as store_slug, s.name as store_name,
            s.country_code as store_country, s.website as store_website,
            s.active as store_active,
            pr.price
        from store_products sp
        join catalog_products cp on cp.id = sp.product_id
        join stores s on s.id = sp.store_id
        join current_prices pr on pr.store_product_id = sp.id
        where {' and '.join(clauses)}
        """,
        tuple(params),
    )


# --------------------------------------------------------------- admin

def list_scrape_runs(limit: int = 50, store: str | None = None) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if store:
        clauses.append("s.slug = %s")
        params.append(store)
    where = ("where " + " and ".join(clauses)) if clauses else ""
    return fetch_all(
        f"""
        select r.id, s.slug as store_slug, r.adapter, r.status,
               r.started_at, r.finished_at, r.products_found,
               r.products_new, r.prices_written, r.errors, r.notes
        from scrape_runs r
        join stores s on s.id = r.store_id
        {where}
        order by r.started_at desc
        limit %s
        """,
        (*params, limit),
    )


def get_scrape_run(run_id: int) -> dict | None:
    return fetch_one(
        """
        select r.id, s.slug as store_slug, r.adapter, r.status,
               r.started_at, r.finished_at, r.products_found,
               r.products_new, r.prices_written, r.errors, r.notes
        from scrape_runs r
        join stores s on s.id = r.store_id
        where r.id = %s
        """,
        (run_id,),
    )


def get_catalog_stats() -> dict:
    row = fetch_one(
        """
        select
            (select count(*) from stores where active) as stores,
            (select count(*) from catalog_products) as products,
            (select count(*) from store_products) as store_products,
            (select count(*) from prices) as prices,
            (select count(*) from (
                select product_id from store_products
                where product_id is not null
                group by product_id having count(distinct store_id) > 1
            ) t) as products_multi_store,
            (select count(*) from store_products where needs_review) as needs_review
        """
    )
    last = fetch_one(
        """
        select s.slug as store_slug, r.status, r.finished_at, r.products_found
        from scrape_runs r join stores s on s.id = r.store_id
        where r.finished_at is not null
        order by r.finished_at desc limit 1
        """
    )
    stats = dict(row or {})
    stats["last_ingest"] = last
    return stats
