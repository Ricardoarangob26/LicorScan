from __future__ import annotations

from fastapi import APIRouter, Query

from apiserver import repositories as repo
from apiserver.errors import store_not_found
from apiserver.schemas import ErrorResponse

router = APIRouter(tags=["tiendas"])


@router.get(
    "/stores",
    summary="Listar tiendas",
    description=(
        "Las tiendas son datos, no código. Usa este endpoint para poblar "
        "filtros en lugar de codificar la lista en el cliente."
    ),
)
async def list_stores(
    active: bool = Query(True, description="Solo tiendas activas"),
):
    rows = repo.list_stores(active_only=active)
    return {"data": rows, "meta": {"returned": len(rows)}}


@router.get(
    "/stores/{slug}",
    summary="Detalle de una tienda",
    responses={404: {"model": ErrorResponse, "description": "La tienda no existe"}},
)
async def get_store(slug: str):
    store = repo.get_store(slug)
    if not store:
        raise store_not_found(slug)
    return {"data": store}


@router.get(
    "/stores/{slug}/products",
    summary="Productos de una tienda",
    responses={404: {"model": ErrorResponse, "description": "La tienda no existe"}},
)
async def store_products(
    slug: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if not repo.get_store(slug):
        raise store_not_found(slug)
    rows, total = repo.list_products(limit=limit, offset=offset, store=slug)
    return {
        "data": rows,
        "meta": {"limit": limit, "offset": offset, "total": total, "returned": len(rows)},
    }
