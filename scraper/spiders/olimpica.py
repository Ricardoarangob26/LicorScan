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
    PRICE_SELECTOR = '[class*="sellingPriceValue"], [class*="price"]'
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
        await self.goto_with_retry(page, url)
        await page.wait_for_selector(self.PRODUCT_SELECTOR, timeout=20_000)

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

            price_raw = await self._extract_price_text(card)
            img_src = await self._safe_attr(card, self.IMAGE_SELECTOR, "src")

            detail_url = await self._resolve_detail_url(page, card)
            if not detail_url or detail_url in seen:
                continue

            seen.add(detail_url)
            new_count += 1

            price_raw = self._clean_price_text(price_raw)
            price_cop = self.parse_cop_price(price_raw) if price_raw else None
            if price_cop is None:
                detail_price_raw = await self._fetch_detail_price(page, detail_url)
                detail_price_raw = self._clean_price_text(detail_price_raw)
                price_cop = self.parse_cop_price(detail_price_raw) if detail_price_raw else None

            self.add_product(
                ScrapedProduct(
                    store=self.store_id,
                    store_name=self.store_name,
                    name=name,
                    price_cop=price_cop,
                    url=detail_url,
                    image_url=img_src,
                    category=category,
                    source_page_url=page.url,
                )
            )

        logger.info(f"[{self.store_id}] '{category}': {count} visibles, {new_count} nuevos")

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

    async def _extract_price_text(self, card) -> str:
        price_locator = card.locator(self.PRICE_SELECTOR)
        texts = [text.strip() for text in await price_locator.all_text_contents() if text and text.strip()]
        for text in texts:
            if re.search(r"\$\s*(?:\d{1,3}(?:[.,]\d{3})+|\d{4,})", text):
                return text
        for text in texts:
            if "$" in text and re.search(r"\d", text):
                return text
        return ""

    async def _fetch_detail_price(self, page: Page, detail_url: str) -> str:
                return await page.evaluate(
                        """
                        async (targetUrl) => {
                            try {
                                const response = await fetch(targetUrl, { credentials: 'include' });
                                const html = await response.text();
                                const document = new DOMParser().parseFromString(html, 'text/html');
                                const meta = document.querySelector('meta[property="product:price:amount"]');
                                if (meta && meta.content) {
                                    return `$ ${meta.content}`;
                                }
                                const ldJson = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
                                    .map((node) => node.textContent || '')
                                    .find((text) => text.includes('"offers"'));
                                if (ldJson) {
                                    const data = JSON.parse(ldJson);
                                    const offer = data.offers && (Array.isArray(data.offers) ? data.offers[0] : data.offers);
                                    if (offer && offer.price) {
                                        return `$ ${offer.price}`;
                                    }
                                }
                            } catch (error) {
                                return '';
                            }
                            return '';
                        }
                        """,
                        detail_url,
                )

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