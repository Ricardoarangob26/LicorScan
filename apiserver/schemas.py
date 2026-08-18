"""Modelos de respuesta.

Todas las respuestas comparten forma:

    éxito -> {"data": ..., "meta": {...}}
    error -> {"error": {"code": "...", "message": "..."}}
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ---------- Envolturas ----------

class Meta(BaseModel):
    limit: int | None = None
    offset: int | None = None
    total: int | None = None
    returned: int | None = None


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta | None = None


class ErrorBody(BaseModel):
    code: str = Field(examples=["PRODUCT_NOT_FOUND"])
    message: str = Field(examples=["Product not found"])


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------- Entidades ----------

class Store(BaseModel):
    id: int
    slug: str
    name: str
    country_code: str
    website: str | None = None
    active: bool


class Brand(BaseModel):
    id: int
    slug: str
    name: str
    product_count: int | None = None


class Category(BaseModel):
    id: int
    slug: str
    name: str
    parent_id: int | None = None
    product_count: int | None = None


class StorePrice(BaseModel):
    store: Store
    price: float
    list_price: float | None = Field(
        default=None, description="Precio antes del descuento. Nulo si no hay promoción."
    )
    discount_pct: float | None = None
    currency: str
    available: bool
    url: str
    updated_at: datetime


class Product(BaseModel):
    id: int
    name: str
    barcode: str | None = None
    brand: Brand | None = None
    category: Category | None = None
    quantity: float | None = None
    unit: str | None = None
    image_url: str | None = None
    store_count: int = Field(default=0, description="En cuántas tiendas se encontró")
    min_price: float | None = None
    max_price: float | None = None


class ProductDetail(Product):
    prices: list[StorePrice] = []
    cheapest: StorePrice | None = None


class PricePoint(BaseModel):
    store_slug: str
    price: float
    list_price: float | None = None
    available: bool
    captured_at: datetime


class PriceHistory(BaseModel):
    product_id: int
    product_name: str
    points: list[PricePoint]
    min_price: float | None = None
    max_price: float | None = None
    avg_price: float | None = None


# ---------- Comparación de carrito ----------

class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=999)


class CartRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=100)
    stores: list[str] | None = Field(
        default=None, description="Slugs a considerar. Si se omite, todas."
    )


class CartLine(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float | None = None
    subtotal: float | None = None
    available: bool


class CartStoreResult(BaseModel):
    store: Store
    total: float
    items_available: int
    items_missing: int
    lines: list[CartLine]


class CartBestPerItem(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    store_slug: str
    unit_price: float
    subtotal: float


class CartComparison(BaseModel):
    results: list[CartStoreResult]
    best_store: str | None = None
    best_total: float | None = None
    worst_total: float | None = None
    saving: float | None = Field(
        default=None, description="Diferencia entre la tienda más cara y la más barata"
    )
    cherry_pick: list[CartBestPerItem] = Field(
        default_factory=list,
        description="Comprando cada producto donde esté más barato",
    )
    cherry_pick_total: float | None = None
    cherry_pick_saving: float | None = Field(
        default=None, description="Ahorro frente a comprar todo en la tienda más barata"
    )


# ---------- Administración ----------

class ScrapeRun(BaseModel):
    id: int
    store_slug: str
    adapter: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    products_found: int
    products_new: int
    prices_written: int
    errors: int
    notes: str | None = None


class HealthStatus(BaseModel):
    status: str
    version: str
    database: str
    environment: str


class CatalogStats(BaseModel):
    stores: int
    products: int
    store_products: int
    prices: int
    products_multi_store: int = Field(
        description="Productos encontrados en más de una tienda (comparables)"
    )
    needs_review: int
    last_ingest: dict[str, Any] | None = None
