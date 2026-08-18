"""Pool de conexiones de solo lectura para la API.

La API nunca escribe ni dispara scraping: sirve lo que el pipeline de
ingesta ya dejó en la base. Esa separación es lo que mantiene los
tiempos de respuesta bajos y predecibles.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool
from loguru import logger

from apiserver.settings import get_settings

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("Falta SUPABASE_DB_URL")
    _pool = psycopg2.pool.ThreadedConnectionPool(
        settings.pool_min,
        settings.pool_max,
        settings.database_url,
        connect_timeout=15,
    )
    logger.info(f"Pool de BD listo ({settings.pool_min}-{settings.pool_max} conexiones)")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Pool de BD cerrado")


@contextmanager
def get_cursor():
    """Cursor que devuelve dicts. La conexión vuelve siempre al pool."""
    if _pool is None:
        raise RuntimeError("El pool de BD no está inicializado")
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        # Solo lectura, pero cerrar la transacción evita dejar
        # conexiones en 'idle in transaction'.
        conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def fetch_all(query: str, params: Any = None) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_one(query: str, params: Any = None) -> dict | None:
    with get_cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_value(query: str, params: Any = None) -> Any:
    with get_cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if not row:
            return None
        return next(iter(row.values()))


def healthcheck() -> bool:
    try:
        return fetch_value("select 1") == 1
    except Exception as exc:
        logger.error(f"Healthcheck de BD falló: {exc!r}")
        return False
