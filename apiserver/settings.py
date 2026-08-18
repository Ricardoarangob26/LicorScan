"""Configuración por variables de entorno. Nada de credenciales en código."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self) -> None:
        load_dotenv(BASE_DIR / ".env")

        self.environment: str = os.getenv("ENVIRONMENT", "development")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.database_url: str = os.getenv("SUPABASE_DB_URL", "")

        # Orígenes permitidos, separados por coma. '*' solo en desarrollo.
        raw_origins = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        # Punto de extensión para autenticación: mientras esté vacío, la
        # API es pública de solo lectura. Al definir API_KEY, los
        # endpoints de administración la exigen.
        self.api_key: str | None = os.getenv("API_KEY") or None

        self.pool_min: int = int(os.getenv("DB_POOL_MIN", "1"))
        self.pool_max: int = int(os.getenv("DB_POOL_MAX", "8"))

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
