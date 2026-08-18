"""Errores con forma consistente en todos los endpoints."""
from __future__ import annotations

from fastapi import HTTPException


class ApiError(HTTPException):
    """Error de dominio con código estable, apto para clientes.

    El `code` es parte del contrato: un cliente puede ramificar sobre él
    sin parsear el mensaje, que es para humanos y puede cambiar.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


class NotFound(ApiError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(404, code, message)


class BadRequest(ApiError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(400, code, message)


class Unauthorized(ApiError):
    def __init__(self, message: str = "Missing or invalid API key") -> None:
        super().__init__(401, "UNAUTHORIZED", message)


def product_not_found(product_id: int) -> NotFound:
    return NotFound("PRODUCT_NOT_FOUND", f"Product {product_id} not found")


def store_not_found(slug: str) -> NotFound:
    return NotFound("STORE_NOT_FOUND", f"Store '{slug}' not found")


def run_not_found(run_id: int) -> NotFound:
    return NotFound("SCRAPE_RUN_NOT_FOUND", f"Scrape run {run_id} not found")
