"""Aplicación FastAPI.

    uvicorn apiserver.main:app --reload

Documentación en /docs (Swagger) y /redoc.
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from apiserver import __version__, database
from apiserver.errors import ApiError
from apiserver.routers import admin, catalog, compare, products, stores
from apiserver.settings import get_settings

DESCRIPTION = """
API de precios de licores y consumibles en supermercados de Colombia.

Los datos vienen de un pipeline de ingesta que corre aparte: **la API
nunca dispara scraping**, solo sirve lo que ya está en la base. Por eso
los tiempos de respuesta no dependen de las tiendas.

* Precios con historial: cada observación se guarda, no se sobrescribe.
* Identidad entre tiendas por código de barras, lo que permite comparar
  el mismo producto en Éxito, Carulla, Olímpica y D1.
* Respuestas con forma constante: `{data, meta}` en éxito,
  `{error: {code, message}}` en error.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    database.init_pool()
    logger.info(f"API v{__version__} lista ({settings.environment})")
    yield
    database.close_pool()


app = FastAPI(
    title="LicorScan API",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- errores

@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    message = first.get("msg", "Invalid request")
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "VALIDATION_ERROR",
            "message": f"{field}: {message}" if field else message,
        }},
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    # El detalle va al log, nunca al cliente: un stack trace en la
    # respuesta filtra estructura interna.
    logger.exception(f"Error no controlado en {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
    )


# ---------------------------------------------------------------- rutas

@app.get("/health", tags=["sistema"], summary="Estado del servicio")
async def health():
    db_ok = database.healthcheck()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": "ok" if db_ok else "unreachable",
        "environment": get_settings().environment,
    }


@app.get("/", include_in_schema=False)
async def root():
    return {"data": {"name": "LicorScan API", "version": __version__, "docs": "/docs"}}


API_V1 = "/api/v1"
app.include_router(stores.router, prefix=API_V1)
app.include_router(products.router, prefix=API_V1)
app.include_router(catalog.router, prefix=API_V1)
app.include_router(compare.router, prefix=API_V1)
app.include_router(admin.router, prefix=API_V1)
