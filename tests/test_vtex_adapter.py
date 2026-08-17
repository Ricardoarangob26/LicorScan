"""Tests del adaptador VTEX sobre respuestas reales recortadas.

No tocan la red: el objetivo es fijar el contrato de traducción entre lo
que devuelve VTEX y el modelo normalizado.
"""
from __future__ import annotations

from core.adapters.vtex import VTEXAdapter, _parse_total
from core.models import StoreConfig

CONFIG = StoreConfig(
    slug="olimpica",
    name="Olímpica",
    base_url="https://www.olimpica.com",
    category_ids=[900080000],
)

# Recorte de una respuesta real: producto en promoción.
ENTRY_EN_PROMO = {
    "productId": "2391082",
    "productName": "Whisky Buchanan's Master Deluxe 750 Ml",
    "brand": "Buchanan'S",
    "linkText": "whisky-buchanans-master-deluxe-750-ml",
    "categories": ["/Supermercado/Licores/Whisky/", "/Supermercado/Licores/", "/Supermercado/"],
    "items": [
        {
            "itemId": "728209",
            "ean": "5000196003774",
            "nameComplete": "Whisky Buchanan's Master Deluxe 750 Ml",
            "images": [{"imageUrl": "https://olimpica.vtexassets.com/x.png"}],
            "sellers": [
                {
                    "commertialOffer": {
                        "Price": 168000.0,
                        "ListPrice": 210000.0,
                        "AvailableQuantity": 100,
                        "Teasers": [],
                    }
                }
            ],
        }
    ],
}


def _adapter() -> VTEXAdapter:
    return VTEXAdapter(CONFIG)


class TestTraduccion:
    def test_producto_en_promocion(self):
        productos = list(_adapter()._to_products(ENTRY_EN_PROMO))
        assert len(productos) == 1
        p = productos[0]

        assert p.store_slug == "olimpica"
        assert p.sku == "728209"
        assert p.barcode == "5000196003774"
        assert p.brand == "Buchanan'S"
        assert p.quantity == 750.0
        assert p.unit == "ml"
        assert p.category_path == "Supermercado/Licores/Whisky"

    def test_precio_de_venta_y_precio_antes(self):
        p = next(iter(_adapter()._to_products(ENTRY_EN_PROMO)))
        # El precio que se guarda es el que realmente se cobra.
        assert p.price.price == 168000.0
        assert p.price.list_price == 210000.0
        assert p.price.has_discount is True

    def test_sin_promocion_no_hay_list_price(self):
        """Si ListPrice no supera a Price, no es promoción."""
        entry = _clonar(ENTRY_EN_PROMO, price=210000.0, list_price=210000.0)
        p = next(iter(_adapter()._to_products(entry)))
        assert p.price.list_price is None
        assert p.price.has_discount is False

    def test_descarta_producto_sin_precio(self):
        entry = _clonar(ENTRY_EN_PROMO, price=None)
        assert list(_adapter()._to_products(entry)) == []

    def test_descarta_precio_cero(self):
        entry = _clonar(ENTRY_EN_PROMO, price=0.0)
        assert list(_adapter()._to_products(entry)) == []

    def test_ean_invalido_queda_en_none(self):
        entry = _clonar(ENTRY_EN_PROMO, ean="0")
        p = next(iter(_adapter()._to_products(entry)))
        assert p.barcode is None

    def test_url_absoluta_desde_linktext(self):
        p = next(iter(_adapter()._to_products(ENTRY_EN_PROMO)))
        assert p.url == "https://www.olimpica.com/whisky-buchanans-master-deluxe-750-ml/p"

    def test_disponibilidad(self):
        entry = _clonar(ENTRY_EN_PROMO, available=0)
        p = next(iter(_adapter()._to_products(entry)))
        assert p.price.available is False


class TestParseTotal:
    def test_cabecera_resources(self):
        assert _parse_total({"resources": "0-49/4401"}) == 4401

    def test_cabecera_ausente_o_rara(self):
        assert _parse_total({}) is None
        assert _parse_total({"resources": "raro"}) is None


def _clonar(entry: dict, **cambios) -> dict:
    """Copia la respuesta de ejemplo cambiando campos de la oferta."""
    import copy

    clon = copy.deepcopy(entry)
    item = clon["items"][0]
    offer = item["sellers"][0]["commertialOffer"]
    if "price" in cambios:
        offer["Price"] = cambios["price"]
    if "list_price" in cambios:
        offer["ListPrice"] = cambios["list_price"]
    if "available" in cambios:
        offer["AvailableQuantity"] = cambios["available"]
    if "ean" in cambios:
        item["ean"] = cambios["ean"]
    return clon
