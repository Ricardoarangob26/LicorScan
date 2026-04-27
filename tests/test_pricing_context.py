from scraper.pricing_context import build_pricing_context


def test_build_pricing_context_detects_discount_and_holiday_signal():
    history = [
        {"date": "2025-12-20", "price": 50000},
        {"date": "2025-12-24", "price": 50000},
        {"date": "2025-12-25", "price": 42000},
        {"date": "2025-12-26", "price": 42000},
    ]

    context = build_pricing_context(history)

    assert context["has_discount"] is True
    assert context["reference_price"] == 50000.0
    assert context["current_price"] == 42000.0
    assert context["discount_start"] == "2025-12-25"
    assert context["discount_observed_until"] == "2025-12-26"
    assert context["discount_pct"] == 16.0
    assert any(signal["kind"] == "holiday" for signal in context["signals"])