from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from scraper.config import STORES
from scraper.spiders.base import BaseSpider, ScrapedProduct


class CarullaSpider(BaseSpider):
    store_id = "carulla"
    store_name = "Carulla"
    base_url = STORES["carulla"]["base_url"]
    delay_seconds = STORES["carulla"]["delay_seconds"]

    categories = STORES["carulla"]["categories"]

    PRODUCT_SELECTOR = 'a.productCard_productLinkInfo__It3J2[href*="/p"]'
    PRICE_SELECTOR = 'p[class*="ProductPrice_container__price"]'
    IMAGE_SELECTOR = "img[src]"

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

            cards = page.locator(self.PRODUCT_SELECTOR)
            count = await cards.count()
            new_count = 0

            for i in range(count):
                card = cards.nth(i)
                href = await card.get_attribute("href")
                absolute_url = self._absolute_url(href)
                if not absolute_url or absolute_url in seen:
                    continue
                seen.add(absolute_url)
                new_count += 1

                text = " ".join((await card.text_content() or "").split())
                name = await self._safe_text(card, "h3") or self._extract_name(card, text)
                if not name:
                    continue
                price_raw = await self._safe_text(card, self.PRICE_SELECTOR)
                img_src = await self._safe_attr(card, self.IMAGE_SELECTOR, "src")

                self.add_product(
                    ScrapedProduct(
                        store=self.store_id,
                        store_name=self.store_name,
                        name=name,
                        price_cop=self.parse_cop_price(price_raw),
                        url=absolute_url,
                        image_url=img_src,
                        category=category,
                        subcategory=page.url,
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

    @staticmethod
    def _extract_name(card, text: str) -> str:
        parts = text.split("$")
        return parts[-1].strip() if len(parts) > 1 else text.strip()