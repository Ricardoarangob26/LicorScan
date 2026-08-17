"""Tests de la capa de normalización.

Los casos vienen de títulos reales de las cuatro tiendas: es justo la
variación entre ellos lo que la cascada de identidad tiene que absorber.
"""
from __future__ import annotations

import pytest

from core.normalize import (
    clean_barcode,
    identity_key,
    normalize_text,
    parse_pack_size,
    parse_quantity,
    slugify,
)


class TestNormalizeText:
    def test_quita_tildes_y_mayusculas(self):
        assert normalize_text("Whisky OLD PARR 12 años") == "whisky old parr 12 anos"

    def test_colapsa_espacios_y_puntuacion(self):
        assert normalize_text("Agua  MANANTIAL  (1500  ml)") == "agua manantial 1500 ml"

    def test_vacio(self):
        assert normalize_text(None) == ""
        assert normalize_text("") == ""

    def test_el_mismo_producto_en_dos_tiendas_converge(self):
        exito = normalize_text("Whisky OLD PARR 12 años (750  ml)")
        olimpica = normalize_text("WHISKY OLD PARR 12 AÑOS 750 ML")
        assert exito == olimpica


class TestParseQuantity:
    @pytest.mark.parametrize(
        "titulo,cantidad,unidad",
        [
            ("Whisky Buchanan's Master Deluxe 750 Ml", 750.0, "ml"),
            ("WHISKY OLD PARR 12 AÑOS 750 ML", 750.0, "ml"),
            ("Agua MANANTIAL sin gas botella (1500  ml)", 1500.0, "ml"),
            ("Pasabocas DETODITO mixto (165  gr)", 165.0, "g"),
            ("Arroz Diana 500gr", 500.0, "g"),
        ],
    )
    def test_extrae_cantidad(self, titulo, cantidad, unidad):
        assert parse_quantity(titulo) == (cantidad, unidad)

    def test_convierte_litros_a_ml(self):
        assert parse_quantity("Ron Medellin 1 Litro") == (1000.0, "ml")
        assert parse_quantity("VINO BAG IN BOX 3 L") == (3000.0, "ml")

    def test_convierte_kilos_a_gramos(self):
        assert parse_quantity("Arroz 2 kg") == (2000.0, "g")

    def test_sin_cantidad(self):
        assert parse_quantity("Whisky sin medida") == (None, None)
        assert parse_quantity(None) == (None, None)

    def test_ignora_unidades_de_conteo(self):
        # 'X6 Unds' es tamaño de pack, no el contenido del envase.
        cantidad, unidad = parse_quantity("Cerveza Club Colombia Lata 330 Ml X6 Unds")
        assert (cantidad, unidad) == (330.0, "ml")


class TestParsePackSize:
    def test_detecta_pack(self):
        assert parse_pack_size("Cerveza Club Colombia Lata 330 Ml X6 Unds") == 6

    def test_sin_pack_es_uno(self):
        assert parse_pack_size("Whisky Old Parr 750 Ml") == 1
        assert parse_pack_size(None) == 1

    def test_ignora_valores_absurdos(self):
        assert parse_pack_size("Producto x999") == 1


class TestCleanBarcode:
    def test_ean_valido(self):
        assert clean_barcode("0039383006507") == "0039383006507"
        assert clean_barcode("7702004003539") == "7702004003539"

    @pytest.mark.parametrize("malo", [None, "", "0", "123", "000000000000", "abc"])
    def test_descarta_invalidos(self, malo):
        assert clean_barcode(malo) is None

    def test_limpia_separadores(self):
        assert clean_barcode("770-2004-003539") == "7702004003539"


class TestSlugify:
    def test_basico(self):
        assert slugify("Vinos y Licores") == "vinos-y-licores"
        assert slugify("Éxito") == "exito"

    def test_vacio_tiene_respaldo(self):
        assert slugify("") == "sin-nombre"
        assert slugify(None) == "sin-nombre"


class TestIdentityKey:
    def test_mismo_producto_misma_clave(self):
        a = identity_key("Old Parr", 750.0, "ml", "Whisky OLD PARR 12 años (750 ml)")
        b = identity_key("OLD PARR", 750.0, "ml", "WHISKY OLD PARR 12 AÑOS 750 ML")
        assert a == b

    def test_distinta_cantidad_distinta_clave(self):
        a = identity_key("Old Parr", 750.0, "ml", "Whisky Old Parr")
        b = identity_key("Old Parr", 1000.0, "ml", "Whisky Old Parr")
        assert a != b

    def test_sin_marca_no_revienta(self):
        assert identity_key(None, None, None, "Producto suelto").startswith("sin-marca|")
