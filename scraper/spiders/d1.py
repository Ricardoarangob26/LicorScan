from __future__ import annotations

import re

from loguru import logger
from playwright.async_api import Page

from scraper.config import MAX_PAGES_PER_CATEGORY, STORES
from scraper.spiders.base import BaseSpider, ScrapedProduct


class D1Spider(BaseSpider):
    store_id = "d1"
    store_name = "D1"
    base_url = STORES["d1"]["base_url"]
    delay_seconds = STORES["d1"]["delay_seconds"]

    CATEGORY_ROUTES = {
        "licores": ["/ca/bebidas/licores/BEBIDAS/LICORES"],
        "vinos": ["/ca/bebidas/vinos/BEBIDAS/VINOS"],
        "bebidas": ["/ca/bebidas/BEBIDAS"],
        "snacks": [
            "https://domicilios.tiendasd1.com/ca/alimentos%20y%20despensa/ALIMENTOS%20Y%20DESPENSA?categories=Pasabocas+y+snacks",
        ],
        "dulceria": [
            "https://domicilios.tiendasd1.com/ca/alimentos%20y%20despensa/dulceria/ALIMENTOS%20Y%20DESPENSA/DULCER%C3%8DA",
        ],
    }

    NOISE_TERMS = [
        "bateria",
        "ollas",
        "freidora",
        "triturador",
        "cocina",
        "aseo",
        "limpieza",
        "maquina",
        "electro",
        "mueble",
        "ropa",
        "zapato",
        "juguete",
        "salud",
        "belleza",
        "mascarilla",
        "shampoo",
        "crema",
    ]

    CATEGORY_TERMS = {
        "licores": ["whisky", "cerveza", "ron", "tequila", "vodka", "ginebra", "aguardiente", "licor"],
        "vinos": ["vino", "espumante", "champagne", "champaña", "merlot", "cabernet", "malbec", "sauvignon"],
        "bebidas": ["gaseosa", "soda", "cola", "agua", "hidratante", "isotonica", "jugo", "refresco", "malta", "energizante"],
        "snacks": ["snack", "papas", "pasabocas", "galleta", "chocolate", "mani", "nueces", "chicle", "tajin", "nachos", "doritos"],
        "dulceria": ["dulceria", "dulce", "chupeta", "caramelo", "caramelo", "gomita", "gomitas", "chocolate", "toffee", "confite", "menta"],
    }

    PRODUCT_SELECTOR = 'a.containerCard[href*="/p/"]'
    NAME_SELECTOR = "h3, [aria-label]"
    IMAGE_SELECTOR = "img[src]"

    async def scrape(self, page: Page) -> None:
        for category, routes in self.CATEGORY_ROUTES.items():
            logger.info(f"[{self.store_id}] Scraping categoría '{category}'")
            try:
                await self._scrape_category(page, category, routes)
            except Exception as exc:
                logger.error(f"[{self.store_id}] Error en '{category}': {exc}")
            await self.polite_wait()

    async def _scrape_category(self, page: Page, category: str, routes: list[str]) -> None:
        seen: set[str] = set()
        for route in routes:
            url = route if route.startswith("http") else f"{self.base_url}{route}"
            await self.goto_with_retry(page, url)
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

                text = " ".join((await card.text_content() or "").split())
                name = await self._extract_name(card, text)
                if not name or not self._matches_category(name, category):
                    continue

                price_raw = self._extract_price(text)
                img_src = await self._safe_attr(card, self.IMAGE_SELECTOR, "src")

                seen.add(absolute_url)
                new_count += 1
                self.add_product(
                    ScrapedProduct(
                        store=self.store_id,
                        store_name=self.store_name,
                        name=name,
                        price_cop=self.parse_cop_price(price_raw),
                        url=absolute_url,
                        image_url=img_src,
                        category=category,
                        subcategory=route,
                        source_page_url=page.url,
                    )
                )

            logger.info(f"[{self.store_id}] Ruta '{route}' de '{category}': {count} visibles, {new_count} nuevos")

    @staticmethod
    async def _extract_name(card, text: str) -> str:
        name = await card.locator("h3").first.text_content() if await card.locator("h3").count() else None
        if name:
            return " ".join(name.split()).strip()
        alt = await card.locator("img").first.get_attribute("alt") if await card.locator("img").count() else None
        if alt:
            return " ".join(alt.split()).strip()
        parts = text.split("$")
        return parts[-1].strip() if len(parts) > 1 else text.strip()

    @staticmethod
    def _extract_price(text: str) -> str | None:
        match = re.search(r"\$\s*[\d\.]+(?:,[\d]{2})?", text)
        return match.group(0) if match else None

    @staticmethod
    def _matches_category(name: str, category: str) -> bool:
        lowered = name.lower()
        if any(term in lowered for term in D1Spider.NOISE_TERMS):
            return False
        return any(D1Spider._contains_word(lowered, keyword) for keyword in D1Spider.CATEGORY_TERMS.get(category, []))

    @staticmethod
    def _contains_word(text: str, term: str) -> bool:
        pattern = rf"\b{re.escape(term)}\b"
        return re.search(pattern, text) is not None

    @staticmethod
    def _page_url(base_url: str, page_number: int) -> str:
        if page_number <= 0:
            return base_url
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}page={page_number}"