from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import holidays as py_holidays
except ImportError:  # pragma: no cover
    py_holidays = None


EVENT_WINDOW_DAYS = 7
DEFAULT_MATCHES_FILE = Path(__file__).resolve().parent.parent / "data" / "events" / "real_cartagena_home_matches.json"


@dataclass(frozen=True)
class EventSignal:
    kind: str
    date: str
    label: str
    days_offset: int
    note: str


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _years_from_points(points: list[dict[str, Any]]) -> set[int]:
    years: set[int] = set()
    for point in points:
        point_date = _parse_date(str(point.get("date") or ""))
        if point_date:
            years.add(point_date.year)
    return years


def _build_colombia_holiday_map(years: set[int]) -> dict[date, str]:
    if not years:
        return {}

    if py_holidays is not None:
        try:
            calendar = py_holidays.Colombia(years=sorted(years))
            return {holiday_date: str(holiday_name) for holiday_date, holiday_name in calendar.items()}
        except Exception:
            pass

    def easter_date(year: int) -> date:
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    def next_monday(month: int, day: int, year: int) -> date:
        base = date(year, month, day)
        delta = (7 - base.weekday()) % 7
        return base if delta == 0 else base + timedelta(days=delta)

    holiday_map: dict[date, str] = {}
    for year in years:
        easter = easter_date(year)
        holiday_map.update(
            {
                date(year, 1, 1): "Año Nuevo",
                next_monday(1, 6, year): "Reyes Magos",
                next_monday(3, 19, year): "San José",
                easter - timedelta(days=3): "Jueves Santo",
                easter - timedelta(days=2): "Viernes Santo",
                date(year, 5, 1): "Día del Trabajo",
                next_monday(6, 29, year): "San Pedro y San Pablo",
                next_monday(7, 20, year): "Independencia de Colombia",
                date(year, 8, 7): "Batalla de Boyacá",
                next_monday(8, 15, year): "Asunción de la Virgen",
                next_monday(10, 12, year): "Día de la Raza",
                next_monday(11, 1, year): "Todos los Santos",
                next_monday(11, 11, year): "Independencia de Cartagena",
                date(year, 12, 8): "Inmaculada Concepción",
                date(year, 12, 25): "Navidad",
            }
        )
        ascension = easter + timedelta(days=39)
        holiday_map[next_monday(ascension.month, ascension.day, year)] = "Ascensión del Señor"

        # Fechas móviles principales del calendario colombiano.
        holiday_map[next_monday((easter + timedelta(days=60)).month, (easter + timedelta(days=60)).day, year)] = "Corpus Christi"
        holiday_map[next_monday((easter + timedelta(days=68)).month, (easter + timedelta(days=68)).day, year)] = "Sagrado Corazón"

    return holiday_map


def load_real_cartagena_home_matches(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or DEFAULT_MATCHES_FILE
    if not source.exists():
        return []

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    matches: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, str):
            match_date = _parse_date(item)
            if match_date:
                matches.append({"date": match_date.isoformat(), "label": "Real Cartagena local"})
            continue

        if not isinstance(item, dict):
            continue

        match_date = _parse_date(str(item.get("date") or ""))
        if not match_date:
            continue

        matches.append(
            {
                "date": match_date.isoformat(),
                "label": str(item.get("label") or item.get("opponent") or "Real Cartagena local").strip(),
                "opponent": str(item.get("opponent") or "").strip() or None,
                "venue": str(item.get("venue") or "").strip() or None,
            }
        )

    matches.sort(key=lambda item: item["date"])
    return matches


def _find_nearby_holiday_signals(discount_start: date, holiday_map: dict[date, str]) -> list[EventSignal]:
    signals: list[EventSignal] = []
    for holiday_date, label in holiday_map.items():
        offset = (holiday_date - discount_start).days
        if abs(offset) > EVENT_WINDOW_DAYS:
            continue

        signals.append(
            EventSignal(
                kind="holiday",
                date=holiday_date.isoformat(),
                label=label,
                days_offset=offset,
                note="puente festivo cercano" if offset else "festivo",
            )
        )
    return sorted(signals, key=lambda item: abs(item.days_offset))


def _find_nearby_match_signals(discount_start: date, matches: list[dict[str, Any]]) -> list[EventSignal]:
    signals: list[EventSignal] = []
    for match in matches:
        match_date = _parse_date(str(match.get("date") or ""))
        if not match_date:
            continue

        offset = (match_date - discount_start).days
        if abs(offset) > EVENT_WINDOW_DAYS:
            continue

        venue = str(match.get("venue") or "").strip().lower()
        note = "partido local cercano"
        if venue and "local" not in venue:
            note = f"partido cercano ({venue})"

        signals.append(
            EventSignal(
                kind="match",
                date=match_date.isoformat(),
                label=str(match.get("label") or "Real Cartagena local").strip(),
                days_offset=offset,
                note=note,
            )
        )
    return sorted(signals, key=lambda item: abs(item.days_offset))


def build_pricing_context(
    history: list[dict[str, Any]],
    *,
    home_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    for entry in history:
        point_date = _parse_date(str(entry.get("date") or ""))
        price = entry.get("price")
        if point_date is None or price is None:
            continue
        points.append({"date": point_date, "price": float(price)})

    points.sort(key=lambda item: item["date"])
    if not points:
        return {
            "has_discount": False,
            "reference_price": None,
            "current_price": None,
            "discount_amount": None,
            "discount_pct": None,
            "discount_start": None,
            "discount_observed_until": None,
            "reference_price_note": "precio base observado",
            "signals": [],
        }

    prices = [point["price"] for point in points]
    reference_price = max(prices)
    current_price = prices[-1]
    discount_threshold = reference_price * 0.98
    has_discount = reference_price > 0 and current_price < discount_threshold

    discount_start: date | None = None
    discount_observed_until: date | None = None
    if has_discount:
        start_index = len(points) - 1
        while start_index > 0 and abs(points[start_index - 1]["price"] - current_price) < 0.01:
            start_index -= 1
        discount_start = points[start_index]["date"]
        discount_observed_until = points[-1]["date"]

    discount_amount = reference_price - current_price if has_discount else None
    discount_pct = (discount_amount / reference_price * 100) if has_discount and reference_price else None

    years = _years_from_points(points)
    holiday_map = _build_colombia_holiday_map(years)
    signals: list[EventSignal] = []
    if discount_start is not None:
        signals.extend(_find_nearby_holiday_signals(discount_start, holiday_map))
        signals.extend(_find_nearby_match_signals(discount_start, home_matches or []))

    return {
        "has_discount": has_discount,
        "reference_price": reference_price,
        "current_price": current_price,
        "discount_amount": round(discount_amount, 2) if discount_amount is not None else None,
        "discount_pct": round(discount_pct, 2) if discount_pct is not None else None,
        "discount_start": discount_start.isoformat() if discount_start else None,
        "discount_observed_until": discount_observed_until.isoformat() if discount_observed_until else None,
        "reference_price_note": "precio base observado",
        "signals": [signal.__dict__ for signal in signals],
    }