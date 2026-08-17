"""Normalización de texto y de cantidades.

Es la base de la cascada de identidad: dos tiendas escriben el mismo
producto de formas distintas, y aquí se reducen a algo comparable.

    Éxito    "Whisky OLD PARR 12 años 12 Años (750  ml)"
    Olímpica "WHISKY OLD PARR 12 AÑOS 750 ML"
             -> "whisky old parr 12 anos 12 anos" + (750, 'ml')
"""
from __future__ import annotations

import re
import unicodedata

# Unidades reconocidas y su forma canónica.
_UNIT_CANONICAL = {
    "ml": "ml", "mililitro": "ml", "mililitros": "ml", "cc": "ml",
    "l": "ml", "lt": "ml", "lts": "ml", "litro": "ml", "litros": "ml",
    "g": "g", "gr": "g", "grs": "g", "gramo": "g", "gramos": "g",
    "kg": "g", "kilo": "g", "kilos": "g", "kilogramo": "g",
    "und": "und", "unidad": "und", "unidades": "und", "un": "und", "unds": "und",
}
# Factores para llevar todo a la unidad canónica (ml y g).
_UNIT_FACTOR = {
    "l": 1000, "lt": 1000, "lts": 1000, "litro": 1000, "litros": 1000,
    "kg": 1000, "kilo": 1000, "kilos": 1000, "kilogramo": 1000,
}

_QTY_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(_UNIT_CANONICAL, key=len, reverse=True)) + r")(?![a-z])",
    re.IGNORECASE,
)
# "x6", "X 6 unds", "6 pack"
_PACK_PATTERN = re.compile(r"\bx\s*(\d{1,2})\b|\b(\d{1,2})\s*pack\b", re.IGNORECASE)


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize_text(text: str | None) -> str:
    """Minúsculas, sin tildes, sin puntuación, espacios colapsados."""
    if not text:
        return ""
    out = strip_accents(str(text)).lower()
    out = re.sub(r"[^\w\s]", " ", out)
    return " ".join(out.split())


def slugify(text: str | None) -> str:
    base = normalize_text(text)
    return re.sub(r"\s+", "-", base).strip("-") or "sin-nombre"


def parse_quantity(title: str | None) -> tuple[float | None, str | None]:
    """Extrae (cantidad, unidad) del título, normalizada a ml o g.

    Devuelve la última coincidencia con unidad de volumen/peso, que en
    los títulos de estas tiendas suele ser la del contenido real.
    Ignora las unidades de conteo ('und'), que se tratan como pack.
    """
    if not title:
        return None, None

    flat = strip_accents(str(title)).lower()
    best: tuple[float, str] | None = None

    for raw_value, raw_unit in _QTY_PATTERN.findall(flat):
        unit_key = raw_unit.lower()
        canonical = _UNIT_CANONICAL.get(unit_key)
        if canonical in (None, "und"):
            continue
        try:
            value = float(raw_value.replace(",", "."))
        except ValueError:
            continue
        value *= _UNIT_FACTOR.get(unit_key, 1)
        best = (value, canonical)

    if best is None:
        return None, None
    return best[0], best[1]


def parse_pack_size(title: str | None) -> int:
    """Cuántas unidades trae el empaque. 1 si no se detecta."""
    if not title:
        return 1
    match = _PACK_PATTERN.search(strip_accents(str(title)).lower())
    if not match:
        return 1
    value = match.group(1) or match.group(2)
    try:
        size = int(value)
    except (TypeError, ValueError):
        return 1
    return size if 1 < size <= 48 else 1


def clean_barcode(raw: str | None) -> str | None:
    """Descarta EAN vacíos o claramente inválidos.

    Algunas tiendas rellenan el campo con ceros o con un solo dígito.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) < 8 or len(digits) > 14:
        return None
    if set(digits) == {"0"}:
        return None
    return digits


def identity_key(brand: str | None, quantity: float | None, unit: str | None, title: str) -> str:
    """Clave de agrupación para productos sin código de barras."""
    parts = [normalize_text(brand) or "sin-marca"]
    if quantity and unit:
        parts.append(f"{quantity:g}{unit}")
    else:
        parts.append("sin-cantidad")
    parts.append(normalize_text(title))
    return "|".join(parts)
