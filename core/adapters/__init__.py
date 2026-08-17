from core.adapters.base import StoreAdapter
from core.adapters.vtex import VTEXAdapter

__all__ = ["StoreAdapter", "VTEXAdapter", "get_adapter"]

_ADAPTERS = {
    "vtex": VTEXAdapter,
}


def get_adapter(platform: str):
    """Devuelve la clase de adaptador para una plataforma.

    Las tiendas son configuración, no código: agregar una tienda VTEX
    nueva no requiere escribir una clase.
    """
    try:
        return _ADAPTERS[platform]
    except KeyError:
        raise ValueError(f"Plataforma sin adaptador: {platform!r}. Disponibles: {list(_ADAPTERS)}")
