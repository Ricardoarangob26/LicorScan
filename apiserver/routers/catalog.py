from __future__ import annotations

from fastapi import APIRouter, Query

from apiserver import repositories as repo

router = APIRouter(tags=["catálogo"])


@router.get(
    "/brands",
    summary="Listar marcas",
    description="Ordenadas por cantidad de productos, para poblar filtros.",
)
async def list_brands(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    rows, total = repo.list_brands(limit=limit, offset=offset)
    return {
        "data": rows,
        "meta": {"limit": limit, "offset": offset, "total": total, "returned": len(rows)},
    }


@router.get(
    "/categories",
    summary="Listar categorías",
    description=(
        "Árbol de categorías con `parent_id`. Cada tienda trae su propia "
        "jerarquía, así que puede haber ramas equivalentes con nombres "
        "distintos; unificarlas es trabajo pendiente."
    ),
)
async def list_categories():
    rows = repo.list_categories()
    return {"data": rows, "meta": {"returned": len(rows)}}
