"""Endpoints de administración: salud de los datos.

Protegidos por API key solo si `API_KEY` está definida. Mientras no lo
esté, la API es pública de solo lectura y estos endpoints también.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query

from apiserver import repositories as repo
from apiserver.errors import Unauthorized, run_not_found
from apiserver.schemas import ErrorResponse
from apiserver.settings import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_key
    if expected and x_api_key != expected:
        raise Unauthorized()


router = APIRouter(tags=["administración"], dependencies=[Depends(require_api_key)])


@router.get(
    "/admin/scrapes",
    summary="Corridas de ingesta",
    description=(
        "Historial de corridas con conteos y estado. Sirve para detectar "
        "un adaptador roto: una corrida `completed` con 0 productos es "
        "tan sospechosa como una `failed`."
    ),
)
async def list_scrapes(
    limit: int = Query(50, ge=1, le=200),
    store: str | None = Query(None, description="Slug de tienda"),
):
    rows = repo.list_scrape_runs(limit=limit, store=store)
    return {"data": rows, "meta": {"returned": len(rows)}}


@router.get(
    "/admin/scrapes/{run_id}",
    summary="Detalle de una corrida",
    responses={404: {"model": ErrorResponse, "description": "La corrida no existe"}},
)
async def get_scrape(run_id: int):
    run = repo.get_scrape_run(run_id)
    if not run:
        raise run_not_found(run_id)
    return {"data": run}


@router.get(
    "/admin/stats",
    summary="Estado del catálogo",
    description=(
        "`products_multi_store` es la métrica que importa para el "
        "comparador: cuántos productos existen en más de una tienda y por "
        "tanto se pueden comparar."
    ),
)
async def catalog_stats():
    return {"data": repo.get_catalog_stats()}
