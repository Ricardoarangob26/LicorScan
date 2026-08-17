"""Contrato común de los adaptadores de tienda."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from core.models import NormalizedProduct, StoreConfig


class StoreAdapter(ABC):
    """Cada origen de datos implementa esto y nada más.

    Quien consume un adaptador no sabe si por debajo hay una API JSON,
    un navegador headless o un archivo: solo recibe NormalizedProduct.
    """

    platform: str

    def __init__(self, config: StoreConfig) -> None:
        self.config = config

    @property
    def slug(self) -> str:
        return self.config.slug

    @abstractmethod
    def fetch_products(self) -> Iterator[NormalizedProduct]:
        """Recorre el catálogo configurado y va emitiendo productos.

        Es un iterador a propósito: permite ir persistiendo por lotes sin
        tener que sostener el catálogo completo en memoria.
        """
        ...

    @abstractmethod
    def discover_categories(self) -> list[dict]:
        """Árbol de categorías de la tienda, para configurarla."""
        ...
