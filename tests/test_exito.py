"""Tests del parser de precios COP.

Ejecutar: pytest tests/
"""
import pytest

from scraper.spiders.base import BaseSpider


class DummySpider(BaseSpider):
    store_id = "dummy"
    store_name = "Dummy"
    base_url = "https://example.com"

    async def scrape(self, page):
        pass


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$ 45.900", 45900.0),
        ("$45.900", 45900.0),
        ("45.900", 45900.0),
        ("45900", 45900.0),
        ("$ 1.234.567", 1234567.0),
        ("45.900,50", 45900.50),
        ("1.234,99", 1234.99),
        ("$ 999", 999.0),
        (45900, 45900.0),
        (45900.5, 45900.5),
        (None, None),
        ("precio no disponible", None),
        ("", None),
    ],
)
def test_parse_cop_price(raw, expected):
    assert DummySpider.parse_cop_price(raw) == expected
