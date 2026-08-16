from __future__ import annotations

import re

from loguru import logger
from playwright.async_api import Page

from scraper.config import STORES
from scraper.spiders.base import BaseSpider, ScrapedProduct


class OlimpicaSpider(BaseSpider):
    store_id = "olimpica"
    store_name = "Olímpica"
    base_url = STORES["olimpica"]["base_url"]
    delay_seconds = STORES["olimpica"]["delay_seconds"]

    categories = {
        "licores": "/supermercado/licores",
    }

    PRODUCT_SELECTOR = "article.vtex-product-summary-2-x-element"
    # VTEX separa el precio realmente cobrado (sellingPrice) del precio de
    # lista tachado (listPriceValue) cuando el producto está en promoción.
    # El selector genérico anterior mezclaba ambos y a veces devolvía el
    # precio de antes del descuento.
    SELLING_PRICE_SELECTOR = '[class*="sellingPrice"]'
    LIST_PRICE_SELECTOR = '[class*="listPriceValue"]'
    IMAGE_SELECTOR = "img[src]"
    LIQUOR_KEYWORDS = (
        "aguardiente",
        "aperitivo",
        "brandy",
        "cerveza",
        "champagne",
        "cognac",
        "coñac",
        "espumante",
        "gin",
        "licor",
        "ron",
        "tequila",
        "vodka",
        "vino",
        "whisky",
        "whiskey",
        "vermut",
    )
    NOISE_TERMS = (
        "cuchara",
        "coctelera",
        "jigger",
        "medidor",
        "mortero",
        "pasta",
        "vaso",
    )

    async def scrape(self, page: Page) -> None:
        for category, path in self.categories.items():
            url = f"{self.base_url}{path}"
            logger.info(f"[{self.store_id}] Scraping categoría '{category}'")
            try:
                await self._scrape_category(page, url, category)
            except Exception as exc:
                logger.error(f"[{self.store_id}] Error en '{category}': {exc}")
            await self.polite_wait()

    async def _scrape_category(self, page: Page, url: str, category: str) -> None:
        seen: set[str] = set()
        page_number = 0
        max_pages = 35

        while page_number < max_pages:
            current_url = self._page_url(url, page_number)
            await self.goto_with_retry(page, current_url)
            await page.wait_for_selector(self.PRODUCT_SELECTOR, timeout=20_000)
            # El widget de precio (selling vs. list price) hidrata unos
            # instantes después de que aparece el card del producto.
            await page.wait_for_timeout(1500)

            cards = page.locator(self.PRODUCT_SELECTOR)
            count = await cards.count()
            new_count = 0

            for i in range(count):
                card = cards.nth(i)
                name = await self._safe_text(card, "h3") or await self._safe_text(card, "[class*='brand'], [class*='name']")
                if not name:
                    continue

                normalized_name = self._normalize_text(name)
                if not self._looks_like_liquor(normalized_name):
                    continue

                selling_price_raw = await self._extract_price_text(card, self.SELLING_PRICE_SELECTOR)
                list_price_raw = await self._extract_price_text(card, self.LIST_PRICE_SELECTOR)
                img_src = await self._safe_attr(card, self.IMAGE_SELECTOR, "src")

                detail_url = await self._resolve_detail_url(page, card)
                if not detail_url or detail_url in seen:
                    continue

                seen.add(detail_url)
                new_count += 1

                selling_price_raw = self._clean_price_text(selling_price_raw)
                price_cop = self.parse_cop_price(selling_price_raw) if selling_price_raw else None

                list_price_raw = self._clean_price_text(list_price_raw)
                list_price_cop = self.parse_cop_price(list_price_raw) if list_price_raw else None

                if price_cop is None:
                    # El precio de venta no hidrató a tiempo en el listado:
                    # ir a la página de detalle (fuente confiable) en vez de
                    # asumir el precio de lista (antes del descuento) como
                    # si fuera el precio real cobrado.
                    detail_price_raw = await self._fetch_detail_price(page, detail_url)
                    detail_price_raw = self._clean_price_text(detail_price_raw)
                    price_cop = self.parse_cop_price(detail_price_raw) if detail_price_raw else None

                if price_cop is None:
                    # Último recurso: no hay forma de confirmar el precio
                    # real, usar el de lista aunque pueda incluir descuento.
                    price_cop = list_price_cop
                    list_price_cop = None

                if list_price_cop is not None and (price_cop is None or list_price_cop <= price_cop):
                    list_price_cop = None

                self.add_product(
                    ScrapedProduct(
                        store=self.store_id,
                        store_name=self.store_name,
                        name=name,
                        price_cop=price_cop,
                        list_price_cop=list_price_cop,
                        url=detail_url,
                        image_url=img_src,
                        category=category,
                        source_page_url=page.url,
                    )
                )

            logger.info(f"[{self.store_id}] Página {page_number} de '{category}': {count} visibles, {new_count} nuevos")
            if new_count == 0:
                break
            page_number += 1

    @staticmethod
    def _page_url(base_url: str, page_number: int) -> str:
        if page_number <= 0:
            return base_url
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}page={page_number}"

    async def _resolve_detail_url(self, page: Page, card) -> str | None:
        """Obtiene la URL del producto desde el anchor que envuelve el card."""
        href = await card.evaluate("(el) => el.closest('a') && el.closest('a').getAttribute('href')")
        absolute_url = self._absolute_url(href)
        if absolute_url:
            return absolute_url

        previous_url = page.url
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
                await card.click()
            detail_url = page.url
            if detail_url == previous_url:
                return None
            await page.go_back(wait_until="domcontentloaded", timeout=15_000)
            await page.wait_for_timeout(2000)
            return detail_url
        except Exception:
            return None

    async def _extract_price_text(self, card, selector: str) -> str:
        price_locator = card.locator(selector)
        texts = [text.strip() for text in await price_locator.all_text_contents() if text and text.strip()]
        for text in texts:
            if re.search(r"\$\s*(?:\d{1,3}(?:[.,]\d{3})+|\d{4,})", text):
                return text
        for text in texts:
            if "$" in text and re.search(r"\d", text):
                return text
        return ""

    async def _fetch_detail_price(self, page: Page, detail_url: str) -> str:
        """Precio confiable desde la página de detalle.

        Olímpica recalcula el precio por JavaScript después de la carga
        inicial (el HTML servido por SSR trae el precio de lista, no el
        de venta). Un fetch() crudo sin ejecutar JS devuelve ese precio
        viejo, así que hay que navegar de verdad en una pestaña aparte.
        """
        detail_page = await page.context.new_page()
        try:
            await detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=20_000)
            await detail_page.wait_for_timeout(1500)
            meta_content = await detail_page.get_attribute('meta[property="product:price:amount"]', "content")
            if meta_content:
                return f"$ {meta_content}"
            for text in await detail_page.locator('[class*="sellingPrice"]').all_text_contents():
                if text and text.strip():
                    return text
        except Exception:
            pass
        finally:
            await detail_page.close()
        return ""

    def _looks_like_liquor(self, normalized_name: str) -> bool:
        if any(term in normalized_name for term in self.NOISE_TERMS):
            return False
        return any(term in normalized_name for term in self.LIQUOR_KEYWORDS)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.lower().split())

    @staticmethod
    def _clean_price_text(text: str) -> str:
        return " ".join(text.replace("Cualquier medio", "").split()) if text else ""