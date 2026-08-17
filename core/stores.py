"""Configuración de tiendas.

Las tiendas son datos, no código: agregar una tienda VTEX nueva es
agregar una entrada aquí, sin escribir una clase ni un `if store ==`.

Los `category_ids` salen del árbol de categorías de cada tienda; se
descubren con:

    py -m core.ingest --discover <slug>
"""
from __future__ import annotations

from core.models import StoreConfig

STORES: dict[str, StoreConfig] = {
    "exito": StoreConfig(
        slug="exito",
        name="Éxito",
        base_url="https://www.exito.com",
        # Vinos y licores (34185780) · Bebidas (346084837)
        category_ids=[34185780, 346084837],
        delay_seconds=3.0,
    ),
    "carulla": StoreConfig(
        slug="carulla",
        name="Carulla",
        base_url="https://www.carulla.com",
        # Vinos y licores (27185082) · Bebidas, snacks y dulces (27185083)
        category_ids=[27185082, 27185083],
        delay_seconds=3.0,
    ),
    "olimpica": StoreConfig(
        slug="olimpica",
        name="Olímpica",
        base_url="https://www.olimpica.com",
        # Licores (900080000) · Bebidas (900090000)
        category_ids=[900080000, 900090000],
        delay_seconds=3.0,
    ),
    "d1": StoreConfig(
        slug="d1",
        name="D1",
        base_url="https://www.d1.com.co",
        # Licor, vinos y más (7) · Bebidas (3)
        category_ids=[7, 3],
        delay_seconds=3.0,
    ),
}


def get_store(slug: str) -> StoreConfig:
    try:
        return STORES[slug]
    except KeyError:
        raise SystemExit(f"Tienda desconocida: {slug!r}. Disponibles: {list(STORES)}")
