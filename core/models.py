"""Modelos normalizados, comunes a todos los adaptadores.

La API nunca ve estructuras específicas de una tienda: los adaptadores
traducen lo que devuelva cada origen a estas dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class NormalizedPrice:
    """Una observación de precio en un momento dado."""

    price: float
    list_price: float | None = None
    currency: str = "COP"
    available: bool = True
    teasers: list[dict[str, Any]] = field(default_factory=list)
    captured_at: str = ""

    def __post_init__(self) -> None:
        if not self.captured_at:
            object.__setattr__(self, "captured_at", datetime.now(timezone.utc).isoformat())

    @property
    def has_discount(self) -> bool:
        return self.list_price is not None and self.list_price > self.price


@dataclass
class NormalizedProduct:
    """Ficha de un producto en una tienda concreta.

    `barcode` es opcional: no todas las tiendas lo entregan, y la capa de
    identidad debe funcionar igual sin él.
    """

    store_slug: str
    sku: str
    title: str
    url: str
    price: NormalizedPrice

    store_product_id: str | None = None
    barcode: str | None = None
    brand: str | None = None
    category_path: str | None = None
    image_url: str | None = None

    # Se rellenan en la normalización, no en el adaptador.
    normalized_title: str = ""
    quantity: float | None = None
    unit: str | None = None

    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class StoreConfig:
    """Configuración de una tienda para su adaptador."""

    slug: str
    name: str
    base_url: str
    platform: str = "vtex"
    country_code: str = "CO"
    sales_channel: int = 1
    delay_seconds: float = 3.0
    # Categorías a recorrer, por id del árbol (fq=C:<id>).
    category_ids: list[int] = field(default_factory=list)
    # Alternativa por ruta. Hace falta porque en algunas tiendas el id
    # del árbol no mapea al índice de productos: en Olímpica
    # fq=C:900080000 devuelve 0 y la ruta 'Supermercado/Licores' 2.087.
    category_paths: list[str] = field(default_factory=list)
