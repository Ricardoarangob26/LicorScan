"""Spider de Éxito (exito.com) - SPA React.

ESTRATEGIA:
1. Primera pasada con HEADLESS=false para abrir DevTools manualmente y:
   - Identificar el endpoint XHR real que devuelve el catálogo
     (probablemente algo como /api/graphql o /api/io/_v/...).
   - Detectar si hay Cloudflare/Akamai challenge.
2. Una vez identificado el endpoint, dos caminos:
   A) Interceptar esa respuesta vía page.on("response") - ya preparado en BaseSpider.
   B) Parsear el DOM renderizado con selectores.

Este archivo implementa el camino B (parseo DOM) como default,
porque es el que siempre funciona aunque cambie el backend.
Cuando identifiquemos el endpoint, se puede optimizar.

NOTA IMPORTANTE: Los selectores de abajo son una PLANTILLA basada
en patrones comunes de VTEX (plataforma que usa Éxito). Hay que
validarlos contra el DOM real en la primera ejecución.
"""
from __future__ import annotations

from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

from loguru import logger
from playwright.async_api import Page

from scraper.config import MAX_PAGES_PER_CATEGORY, STORES
from scraper.spiders.base import BaseSpider, ScrapedProduct


class ExitoSpider(BaseSpider):
    store_id = "exito"
    store_name = "Éxito"
    base_url = STORES["exito"]["base_url"]
    delay_seconds = STORES["exito"]["delay_seconds"]

    # Selectores validados contra el DOM real actual de exito.com.
    PRODUCT_LINK_SELECTOR = "a.productCard_productLinkInfo__It3J2"
    PRODUCT_FALLBACK_LINK_SELECTOR = "a[href*='/p']"
    PRODUCT_NAME_SELECTOR = "h3"
    PRODUCT_PRICE_SELECTOR = "p[class*='ProductPrice_container__price']"
    PRODUCT_IMG_SELECTOR = "img"

    async def scrape(self, page: Page) -> None:
        categories = STORES["exito"]["categories"]
        for category, path in categories.items():
            url = f"{self.base_url}{path}"
            logger.info(f"[{self.store_id}] Scraping categoría '{category}'")
            try:
                await self._scrape_category(page, url, category)
            except Exception as e:
                logger.error(f"[{self.store_id}] Error en '{category}': {e}")
            await self.polite_wait()

    async def _scrape_category(self, page: Page, url: str, category: str) -> None:
        """Scraping de una categoría recorriendo todas las páginas disponibles."""
        seen_urls: set[str] = set()
        page_number = 0
        empty_or_repeated_pages = 0
        max_pages = MAX_PAGES_PER_CATEGORY

        while page_number < max_pages:
            current_url = self._page_url(url, page_number)
            await self.goto_with_retry(page, current_url)

            # SPAs necesitan tiempo extra para hidratar el contenido.
            # Esperar a que aparezca AL MENOS un link de producto o timeout.
            try:
                await page.wait_for_selector(self.PRODUCT_LINK_SELECTOR, timeout=20_000)
            except Exception:
                logger.warning(
                    f"[{self.store_id}] No aparecieron productos con selector "
                    f"'{self.PRODUCT_LINK_SELECTOR}'. Verificar DOM en headed mode."
                )
                html = await page.content()
                snapshot = url.replace("/", "_").replace(":", "")[-80:]
                from scraper.config import OUTPUT_DIR

                (OUTPUT_DIR / f"exito_debug_{snapshot}.html").write_text(html, encoding="utf-8")
                return

            await self._scroll_to_load(page, max_scrolls=3)

            links = await page.locator(self.PRODUCT_LINK_SELECTOR).all()
            if not links:
                links = await page.locator(self.PRODUCT_FALLBACK_LINK_SELECTOR).all()

            page_count = 0
            new_count = 0
            for i, link in enumerate(links):
                try:
                    name = await self._safe_text(link, self.PRODUCT_NAME_SELECTOR)
                    href = await link.get_attribute("href")

                    card_info = link.locator("xpath=ancestor::*[contains(@class,'productCard_productInfo')][1]").first
                    card_content = link.locator("xpath=ancestor::*[contains(@class,'productCard_contentInfo')][1]").first

                    price_raw = await self._safe_text(card_info, self.PRODUCT_PRICE_SELECTOR)
                    img_src = await self._extract_best_image(card_content)
                    absolute_url = self._absolute_url(href)

                    if not name or not absolute_url:
                        continue

                    page_count += 1
                    if absolute_url in seen_urls:
                        continue
                    seen_urls.add(absolute_url)
                    new_count += 1

                    product = ScrapedProduct(
                        store=self.store_id,
                        store_name=self.store_name,
                        name=name,
                        price_cop=self.parse_cop_price(price_raw),
                        url=absolute_url,
                        image_url=img_src,
                        category=category,
                        source_page_url=page.url,
                    )
                    self.add_product(product)
                except Exception as e:
                    logger.warning(f"[{self.store_id}] Card {i} falló: {e}")

            logger.info(
                f"[{self.store_id}] Página {page_number} de '{category}': "
                f"{page_count} visibles, {new_count} nuevos"
            )

            # Corta cuando la paginación incremental deja de traer items nuevos.
            if page_count == 0 or new_count == 0:
                empty_or_repeated_pages += 1
            else:
                empty_or_repeated_pages = 0

            if empty_or_repeated_pages >= 2:
                logger.info(
                    f"[{self.store_id}] Fin paginación en '{category}': "
                    f"{empty_or_repeated_pages} páginas seguidas sin novedades"
                )
                break

            page_number += 1

        if page_number >= max_pages:
            logger.warning(
                f"[{self.store_id}] Se alcanzó tope defensivo de {max_pages} páginas en '{category}'"
            )

    async def _scroll_to_load(self, page: Page, max_scrolls: int = 3) -> None:
        """Scroll progresivo para disparar lazy-load de VTEX."""
        for i in range(max_scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
            await page.wait_for_timeout(1500)

    @staticmethod
    async def _safe_text(locator, selector: str) -> str:
        """Extrae texto del primer match del selector, o '' si no existe."""
        el = locator.locator(selector).first
        if not await el.count():
            return ""
        text = await el.text_content()
        return (text or "").strip()

    @staticmethod
    async def _safe_attr(locator, selector: str, attr: str) -> str | None:
        """Extrae atributo del primer match, o None si no existe."""
        el = locator.locator(selector).first
        if not await el.count():
            return None
        value = await el.get_attribute(attr)
        return (value or "").strip() or None

    @staticmethod
    async def _extract_best_image(locator) -> str | None:
        """Selecciona la mejor imagen de producto y evita sellos/cucardas."""
        images = locator.locator("img")
        total = await images.count()
        if total == 0:
            return None

        candidates: list[str] = []
        for i in range(total):
            img = images.nth(i)
            src = (await img.get_attribute("src") or "").strip()
            data_src = (await img.get_attribute("data-src") or "").strip()
            value = src or data_src
            if value:
                candidates.append(value)

        if not candidates:
            return None

        # En exito.com, las fotos de producto suelen vivir en vtexassets /arquivos/ids.
        for url in candidates:
            lower = url.lower()
            if "vtexassets.com" in lower or "/arquivos/ids/" in lower:
                return url

        blocked_markers = ["sellos", "cucarda", "imprecionantes", "cloudfront.net"]
        for url in candidates:
            lower = url.lower()
            if not any(marker in lower for marker in blocked_markers):
                return url

        return candidates[0]

    @staticmethod
    def _page_url(base_url: str, page_number: int) -> str:
        """Construye la URL de una página específica sin depender de clicks."""
        if page_number <= 0:
            return base_url

        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        if page_number == 0:
            query.pop("page", None)
        else:
            # En Éxito, la página visible 2 corresponde a page=1, la 3 a page=2, etc.
            query["page"] = [str(page_number)]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def _absolute_url(self, href: str | None) -> str | None:
        if not href:
            return None
        if href.startswith("http"):
            return href
        return f"{self.base_url}{href}"
