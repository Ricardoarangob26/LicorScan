from __future__ import annotations

from fastapi import APIRouter, Query

from apiserver import repositories as repo
from apiserver.errors import product_not_found
from apiserver.schemas import ErrorResponse

router = APIRouter(tags=["productos"])


@router.get(
    "/products",
    summary="Listar productos",
    description=(
        "Catálogo unificado. Cada producto puede existir en varias tiendas; "
        "`store_count`, `min_price` y `max_price` resumen esa dispersión. "
        "Con `multi_store=true` se obtienen solo los comparables."
    ),
)
async def list_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    store: str | None = Query(None, description="Slug de tienda"),
    category: str | None = Query(None, description="Slug de categoría"),
    brand: str | None = Query(None, description="Slug de marca"),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    barcode: str | None = Query(None, description="EAN exacto"),
    multi_store: bool = Query(False, description="Solo productos en más de una tienda"),
    sort: str = Query("name", pattern="^(name|price_asc|price_desc|stores)$"),
):
    rows, total = repo.list_products(
        limit=limit, offset=offset, store=store, category=category, brand=brand,
        min_price=min_price, max_price=max_price, barcode=barcode,
        multi_store=multi_store, sort=sort,
    )
    return {
        "data": rows,
        "meta": {"limit": limit, "offset": offset, "total": total, "returned": len(rows)},
    }


@router.get(
    "/products/search",
    summary="Buscar productos",
    description=(
        "Búsqueda difusa por similitud de trigramas, que tolera las "
        "diferencias de escritura entre tiendas: 'old parr' encuentra "
        "tanto 'Whisky OLD PARR 12 años (750 ml)' como "
        "'WHISKY OLD PARR 12 AÑOS 750 ML'."
    ),
)
async def search_products(
    q: str = Query(..., min_length=2, description="Texto a buscar"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    store: str | None = Query(None),
):
    rows, total = repo.search_products(q, limit=limit, offset=offset, store=store)
    return {
        "data": rows,
        "meta": {"limit": limit, "offset": offset, "total": total, "returned": len(rows)},
    }


@router.get(
    "/products/{product_id}",
    summary="Detalle de producto con precios por tienda",
    responses={404: {"model": ErrorResponse, "description": "El producto no existe"}},
)
async def get_product(product_id: int):
    product = repo.get_product(product_id)
    if not product:
        raise product_not_found(product_id)
    prices = repo.get_product_prices(product_id)
    product["prices"] = prices
    product["cheapest"] = prices[0] if prices else None
    return {"data": product}


@router.get(
    "/products/{product_id}/prices",
    summary="Precio del producto en cada tienda",
    description="Ordenado de más barato a más caro. `cheapest` es un atajo al primero.",
    responses={404: {"model": ErrorResponse, "description": "El producto no existe"}},
)
async def get_product_prices(product_id: int):
    product = repo.get_product(product_id)
    if not product:
        raise product_not_found(product_id)
    prices = repo.get_product_prices(product_id)
    return {
        "data": {
            "product": {"id": product["id"], "name": product["name"]},
            "prices": prices,
            "cheapest": prices[0] if prices else None,
        },
        "meta": {"returned": len(prices)},
    }


@router.get(
    "/products/{product_id}/history",
    summary="Historial de precios",
    description=(
        "Serie temporal de todas las observaciones registradas. Cada corrida "
        "de ingesta agrega un punto; nada se sobrescribe."
    ),
    responses={404: {"model": ErrorResponse, "description": "El producto no existe"}},
)
async def get_price_history(
    product_id: int,
    store: str | None = Query(None, description="Slug de tienda"),
    date_from: str | None = Query(None, alias="from", description="ISO 8601"),
    date_to: str | None = Query(None, alias="to", description="ISO 8601"),
    limit: int = Query(1000, ge=1, le=5000),
):
    product = repo.get_product(product_id)
    if not product:
        raise product_not_found(product_id)

    points = repo.get_price_history(product_id, store, date_from, date_to, limit)
    prices = [float(p["price"]) for p in points if p["price"] is not None]
    return {
        "data": {
            "product_id": product_id,
            "product_name": product["name"],
            "points": points,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        },
        "meta": {"returned": len(points)},
    }
