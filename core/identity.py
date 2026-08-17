"""Resolución de identidad de producto entre tiendas.

La regla que manda: cuando no hay certeza, NO se fusiona. Se deja el
producto como entidad aparte y se marca `needs_review`, para que un
humano decida después. Un match equivocado ensucia comparaciones de
precio de forma difícil de detectar; un match faltante solo deja un
producto duplicado, que es visible y reversible.

Cascada, de más fiable a menos:

    1. EAN                         confianza 1.00   automático
    2. brand + cantidad + nombre   confianza 0.80   automático
    3. sin match                   ---              queda para revisión
"""
from __future__ import annotations

from dataclasses import dataclass

from core.models import NormalizedProduct

# Por debajo de esto no se enlaza nada automáticamente.
AUTO_LINK_THRESHOLD = 0.75


@dataclass(frozen=True)
class Match:
    product_id: int | None
    method: str | None
    confidence: float | None
    needs_review: bool


def resolve(conn, repo, product: NormalizedProduct) -> Match:
    """Encuentra o crea el producto canónico para una ficha de tienda."""

    # --- 1. Código de barras: identidad sin ambigüedad ---
    if product.barcode:
        with conn.cursor() as cur:
            cur.execute("select id from catalog_products where barcode = %s", (product.barcode,))
            row = cur.fetchone()
        if row:
            return Match(row[0], "barcode", 1.0, False)
        product_id = _create_canonical(conn, repo, product)
        return Match(product_id, "barcode", 1.0, False)

    # --- 2. Atributos: marca + cantidad + nombre normalizado ---
    brand_id = repo.get_or_create_brand(product.brand)
    if brand_id and product.quantity and product.unit and product.normalized_title:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id from catalog_products
                where brand_id = %s and quantity = %s and unit = %s
                  and normalized_name = %s and barcode is null
                limit 1
                """,
                (brand_id, product.quantity, product.unit, product.normalized_title),
            )
            row = cur.fetchone()
        if row:
            return Match(row[0], "attributes", 0.8, False)

    # --- 3. Sin evidencia suficiente: entidad nueva, marcada ---
    product_id = _create_canonical(conn, repo, product)
    return Match(product_id, None, None, True)


def _create_canonical(conn, repo, product: NormalizedProduct) -> int:
    brand_id = repo.get_or_create_brand(product.brand)
    category_id = repo.get_or_create_category(product.category_path)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into catalog_products (
                barcode, brand_id, category_id, name, normalized_name,
                quantity, unit, image_url
            ) values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (barcode) do update set updated_at = now()
            returning id
            """,
            (
                product.barcode,
                brand_id,
                category_id,
                product.title,
                product.normalized_title,
                product.quantity,
                product.unit,
                product.image_url,
            ),
        )
        return cur.fetchone()[0]


def find_similar_candidates(conn, product: NormalizedProduct, limit: int = 5) -> list[tuple[int, str, float]]:
    """Candidatos por similitud de texto, para revisión manual.

    Deliberadamente NO se usa para enlazar automáticamente: alimenta la
    cola de revisión, donde una persona confirma o descarta.
    """
    if not product.normalized_title:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, name, similarity(normalized_name, %s) as score
            from catalog_products
            where normalized_name %% %s
            order by score desc
            limit %s
            """,
            (product.normalized_title, product.normalized_title, limit),
        )
        return [(r[0], r[1], float(r[2])) for r in cur.fetchall()]
