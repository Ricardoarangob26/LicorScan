"""Comparación de precios entre tiendas.

Es el objetivo central del proyecto: responder "¿dónde me sale más
barato?" tanto para un producto como para una lista de mercado.
"""
from __future__ import annotations

from fastapi import APIRouter

from apiserver import repositories as repo
from apiserver.errors import BadRequest, product_not_found
from apiserver.schemas import CartRequest, ErrorResponse

router = APIRouter(tags=["comparación"])


@router.get(
    "/compare/product/{product_id}",
    summary="Comparar un producto entre tiendas",
    responses={404: {"model": ErrorResponse, "description": "El producto no existe"}},
)
async def compare_product(product_id: int):
    product = repo.get_product(product_id)
    if not product:
        raise product_not_found(product_id)

    prices = repo.get_product_prices(product_id)
    cheapest = prices[0] if prices else None
    most_expensive = prices[-1] if prices else None
    saving = None
    if cheapest and most_expensive and most_expensive["price"] > cheapest["price"]:
        saving = round(most_expensive["price"] - cheapest["price"], 2)

    return {
        "data": {
            "product": {
                "id": product["id"],
                "name": product["name"],
                "barcode": product["barcode"],
            },
            "prices": prices,
            "cheapest": cheapest,
            "most_expensive": most_expensive,
            "saving": saving,
            "stores_compared": len(prices),
        }
    }


@router.post(
    "/compare/cart",
    summary="Comparar una lista de mercado",
    description=(
        "Calcula el total de la lista en cada tienda y además el escenario "
        "de comprar cada producto donde esté más barato (`cherry_pick`), "
        "que suele ahorrar más pero obliga a visitar varias tiendas.\n\n"
        "Solo se consideran tiendas con precio disponible; los productos "
        "que falten en una tienda se reportan en `items_missing` en lugar "
        "de descartar la tienda entera."
    ),
    responses={400: {"model": ErrorResponse, "description": "Petición inválida"}},
)
async def compare_cart(payload: CartRequest):
    quantities = {item.product_id: item.quantity for item in payload.items}
    product_ids = list(quantities)
    if len(product_ids) != len(payload.items):
        raise BadRequest("DUPLICATE_PRODUCT", "Cada product_id debe aparecer una sola vez")

    rows = repo.get_prices_for_products(product_ids, payload.stores)
    if not rows:
        raise BadRequest(
            "NO_PRICES_FOUND",
            "Ningún producto de la lista tiene precio disponible en las tiendas indicadas",
        )

    names = {r["product_id"]: r["product_name"] for r in rows}

    # precio por (tienda, producto)
    by_store: dict[str, dict] = {}
    for row in rows:
        slug = row["store_slug"]
        store = by_store.setdefault(slug, {
            "store": {
                "id": row["store_id"], "slug": slug, "name": row["store_name"],
                "country_code": row["store_country"], "website": row["store_website"],
                "active": row["store_active"],
            },
            "prices": {},
        })
        price = float(row["price"])
        # Una tienda puede listar el mismo producto varias veces; nos
        # quedamos con el precio más bajo, que es el que pagaría el cliente.
        current = store["prices"].get(row["product_id"])
        if current is None or price < current:
            store["prices"][row["product_id"]] = price

    results = []
    for slug, info in by_store.items():
        lines = []
        total = 0.0
        available = 0
        for pid in product_ids:
            qty = quantities[pid]
            unit = info["prices"].get(pid)
            if unit is None:
                lines.append({
                    "product_id": pid, "product_name": names.get(pid, f"#{pid}"),
                    "quantity": qty, "unit_price": None, "subtotal": None,
                    "available": False,
                })
                continue
            subtotal = round(unit * qty, 2)
            total += subtotal
            available += 1
            lines.append({
                "product_id": pid, "product_name": names.get(pid, f"#{pid}"),
                "quantity": qty, "unit_price": unit, "subtotal": subtotal,
                "available": True,
            })
        results.append({
            "store": info["store"],
            "total": round(total, 2),
            "items_available": available,
            "items_missing": len(product_ids) - available,
            "lines": lines,
        })

    # Para elegir "mejor tienda" solo compiten las que tienen todo:
    # una tienda barata a la que le faltan la mitad de los productos no
    # es realmente la más barata.
    complete = [r for r in results if r["items_missing"] == 0]
    ranking = sorted(complete or results, key=lambda r: r["total"])
    best = ranking[0] if ranking else None
    worst = ranking[-1] if ranking else None

    # Escenario "cada cosa donde salga más barata".
    cherry: list[dict] = []
    cherry_total = 0.0
    for pid in product_ids:
        options = [
            (info["prices"][pid], slug)
            for slug, info in by_store.items()
            if pid in info["prices"]
        ]
        if not options:
            continue
        unit, slug = min(options)
        qty = quantities[pid]
        subtotal = round(unit * qty, 2)
        cherry_total += subtotal
        cherry.append({
            "product_id": pid, "product_name": names.get(pid, f"#{pid}"),
            "quantity": qty, "store_slug": slug,
            "unit_price": unit, "subtotal": subtotal,
        })

    cherry_total = round(cherry_total, 2)
    cherry_saving = None
    if best and len(cherry) == len(product_ids):
        cherry_saving = round(best["total"] - cherry_total, 2)

    results.sort(key=lambda r: (r["items_missing"], r["total"]))

    return {
        "data": {
            "results": results,
            "best_store": best["store"]["slug"] if best else None,
            "best_total": best["total"] if best else None,
            "worst_total": worst["total"] if worst else None,
            "saving": round(worst["total"] - best["total"], 2) if best and worst else None,
            "cherry_pick": cherry,
            "cherry_pick_total": cherry_total if cherry else None,
            "cherry_pick_saving": cherry_saving,
        },
        "meta": {
            "items_requested": len(product_ids),
            "stores_compared": len(results),
        },
    }
