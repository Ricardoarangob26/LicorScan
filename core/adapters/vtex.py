"""Adaptador para tiendas montadas sobre VTEX.

Éxito, Carulla, Olímpica y D1 corren sobre VTEX y exponen el mismo
catálogo JSON, así que las cuatro se resuelven con esta clase más un
bloque de configuración por tienda — no con cuatro scrapers distintos.

Frente al scraping de DOM: no hace falta navegador, y la respuesta trae
código de barras, marca, categorías y precio de lista de forma
estructurada, sin selectores frágiles de por medio.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

from loguru import logger

from core.adapters.base import StoreAdapter
from core.models import NormalizedPrice, NormalizedProduct
from core.normalize import clean_barcode, normalize_text, parse_quantity

# VTEX solo devuelve 50 items por petición.
PAGE_SIZE = 50
# Tope defensivo: sin esto, una categoría mal configurada pagina sin fin.
MAX_PAGES_PER_CATEGORY = 120

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class VTEXAdapter(StoreAdapter):
    platform = "vtex"

    # ---- HTTP ----

    def _get(self, path: str, params: dict[str, Any] | None = None, timeout: int = 30):
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self.config.base_url.rstrip('/')}{path}{query}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "es-CO,es;q=0.9",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body), dict(response.headers)

    def _polite_wait(self) -> None:
        time.sleep(self.config.delay_seconds)

    # ---- Categorías ----

    def discover_categories(self, depth: int = 3) -> list[dict]:
        data, _ = self._get(f"/api/catalog_system/pub/category/tree/{depth}")
        return data

    # ---- Catálogo ----

    def fetch_products(self) -> Iterator[NormalizedProduct]:
        if not self.config.category_ids:
            logger.warning(f"[{self.slug}] sin category_ids configurados; no hay nada que traer")
            return

        seen_skus: set[str] = set()
        for category_id in self.config.category_ids:
            yield from self._fetch_category(category_id, seen_skus)

    def _fetch_category(self, category_id: int, seen_skus: set[str]) -> Iterator[NormalizedProduct]:
        offset = 0
        total: int | None = None
        pages = 0

        while pages < MAX_PAGES_PER_CATEGORY:
            params = {
                "fq": f"C:{category_id}",
                # Sin `sc` explícito VTEX devuelve un precio base que no es
                # el que ve el usuario en la web. Verificado en Olímpica:
                # sin sc -> 16.350, con sc=1 -> 17.175 (el de la página).
                "sc": self.config.sales_channel,
                "_from": offset,
                "_to": offset + PAGE_SIZE - 1,
            }
            try:
                data, headers = self._get("/api/catalog_system/pub/products/search", params)
            except urllib.error.HTTPError as exc:
                # VTEX responde 400 cuando el offset supera el máximo permitido.
                logger.warning(f"[{self.slug}] cat {category_id} offset {offset}: HTTP {exc.code}, corto aquí")
                return
            except Exception as exc:
                logger.error(f"[{self.slug}] cat {category_id} offset {offset}: {exc!r}")
                return

            if total is None:
                total = _parse_total(headers)
                logger.info(f"[{self.slug}] categoría {category_id}: {total if total is not None else '?'} productos")

            if not data:
                return

            for entry in data:
                for product in self._to_products(entry):
                    if product.sku in seen_skus:
                        continue
                    seen_skus.add(product.sku)
                    yield product

            offset += PAGE_SIZE
            pages += 1
            if total is not None and offset >= total:
                return
            self._polite_wait()

        logger.warning(f"[{self.slug}] categoría {category_id}: alcanzado el tope de {MAX_PAGES_PER_CATEGORY} páginas")

    # ---- Traducción a modelo normalizado ----

    def _to_products(self, entry: dict[str, Any]) -> Iterator[NormalizedProduct]:
        """Un `product` de VTEX puede traer varios SKUs (items)."""
        product_name = (entry.get("productName") or "").strip()
        brand = (entry.get("brand") or "").strip() or None
        categories = entry.get("categories") or []
        # VTEX ordena de la más específica a la más general.
        category_path = categories[0].strip("/") if categories else None
        link = entry.get("link") or entry.get("linkText")
        store_product_id = str(entry.get("productId") or "") or None

        for item in entry.get("items") or []:
            sku = str(item.get("itemId") or "").strip()
            if not sku:
                continue

            offer = _first_offer(item)
            if offer is None:
                continue

            price = offer.get("Price")
            if price is None or float(price) <= 0:
                # Sin precio utilizable: no inventamos uno.
                continue

            list_price = offer.get("ListPrice")
            if list_price is not None and float(list_price) <= float(price):
                list_price = None

            title = (item.get("nameComplete") or item.get("name") or product_name).strip()
            quantity, unit = parse_quantity(title)

            images = item.get("images") or []
            image_url = images[0].get("imageUrl") if images else None

            yield NormalizedProduct(
                store_slug=self.slug,
                sku=sku,
                store_product_id=store_product_id,
                title=title,
                url=_absolute_url(self.config.base_url, link, entry.get("linkText")),
                barcode=clean_barcode(item.get("ean")),
                brand=brand,
                category_path=category_path,
                image_url=image_url,
                normalized_title=normalize_text(title),
                quantity=quantity,
                unit=unit,
                price=NormalizedPrice(
                    price=float(price),
                    list_price=float(list_price) if list_price is not None else None,
                    available=bool(offer.get("AvailableQuantity", 0)),
                    teasers=offer.get("Teasers") or [],
                ),
                raw={"productId": store_product_id, "itemId": sku},
            )


def _first_offer(item: dict[str, Any]) -> dict[str, Any] | None:
    for seller in item.get("sellers") or []:
        offer = seller.get("commertialOffer")
        if offer:
            return offer
    return None


def _parse_total(headers: dict[str, str]) -> int | None:
    """La cabecera `resources` viene como '0-49/4401'."""
    raw = headers.get("resources") or headers.get("Content-Range") or ""
    if "/" not in raw:
        return None
    try:
        return int(raw.rsplit("/", 1)[1])
    except (ValueError, IndexError):
        return None


def _absolute_url(base_url: str, link: str | None, link_text: str | None) -> str:
    if link and link.startswith("http"):
        return link
    if link_text:
        return f"{base_url.rstrip('/')}/{link_text}/p"
    return base_url
