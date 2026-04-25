"""Spider base: contrato común para todas las tiendas.

Responsabilidades:
- Lanzar Playwright con user-agent rotado.
- Rate limiting por política de cortesía (delay_seconds).
- Interceptación de respuestas XHR/Fetch (para atrapar JSONs internos).
- Retries con backoff exponencial.
- Output consistente en formato Product (dataclass).
"""
from __future__ import annotations

import asyncio
import json
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Response,
    async_playwright,
)
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import HEADLESS, OUTPUT_DIR, OUTPUT_KEEP_LAST, USER_AGENTS


@dataclass
class ScrapedProduct:
    """Producto crudo extraído de una tienda.

    Campos mínimos para primera versión. La normalización (marca,
    volumen, unidad canónica) se hace en el pipeline posterior.
    """
    store: str
    name: str
    price_cop: float | None  # None si no se pudo parsear
    url: str
    image_url: str | None = None
    category: str | None = None
    subcategory: str | None = None
    store_name: str | None = None
    source_page_url: str | None = None
    scraped_at: str = ""
    scraped_date: str = ""
    raw: dict[str, Any] | None = None  # datos crudos del XHR/DOM para debug

    def __post_init__(self) -> None:
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()
        if not self.scraped_date:
            self.scraped_date = self.scraped_at[:10]


class BaseSpider(ABC):
    """Contrato para cada spider de tienda.

    Uso:
        spider = ExitoSpider()
        products = await spider.run()
    """

    # Subclase debe definir estos atributos
    store_id: str  # ej: "exito"
    store_name: str  # ej: "Éxito"
    base_url: str
    delay_seconds: int = 10

    def __init__(self) -> None:
        self._captured_responses: list[dict[str, Any]] = []
        self._products: list[ScrapedProduct] = []

    # ---- Ciclo de vida ----

    async def run(self) -> list[ScrapedProduct]:
        """Orquestador: lanza navegador y ejecuta scrape()."""
        logger.info(f"[{self.store_id}] Iniciando spider (headless={HEADLESS})")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await self._create_context(browser)
            page = await context.new_page()

            # Hook para capturar TODAS las respuestas JSON/XHR
            page.on("response", self._on_response)

            try:
                await self.scrape(page)
            finally:
                await context.close()
                await browser.close()

        self._save_results()
        logger.info(f"[{self.store_id}] Finalizado: {len(self._products)} productos")
        return self._products

    async def _create_context(self, browser: Browser) -> BrowserContext:
        """Crea contexto con UA rotado y viewport realista."""
        ua = random.choice(USER_AGENTS)
        logger.debug(f"[{self.store_id}] User-Agent: {ua[:60]}...")
        return await browser.new_context(
            user_agent=ua,
            viewport={"width": 1366, "height": 768},
            locale="es-CO",
            timezone_id="America/Bogota",
        )

    # ---- Interceptación XHR ----

    async def _on_response(self, response: Response) -> None:
        """Captura respuestas JSON para inspección.

        Motivo: muchos SPAs devuelven catálogos en respuestas XHR/Fetch
        internas. Es más robusto leer esas respuestas que parsear el DOM.
        """
        try:
            ct = (response.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            if response.status != 200:
                return
            url = response.url
            # Heurística: guardar solo URLs que parezcan API/catálogo
            if not any(k in url.lower() for k in ("api", "graphql", "catalog", "product", "search")):
                return
            body = await response.json()
            self._captured_responses.append({"url": url, "body": body})
            logger.debug(f"[{self.store_id}] Captured XHR: {url[:100]}")
        except Exception as e:  # respuestas binarias, expiradas, etc.
            logger.trace(f"[{self.store_id}] Skip response: {e}")

    # ---- Rate limiting ----

    async def polite_wait(self) -> None:
        """Espera con jitter aleatorio para variar el patrón."""
        jitter = random.uniform(-1.5, 1.5)
        wait = max(1.0, self.delay_seconds + jitter)
        logger.debug(f"[{self.store_id}] Polite wait {wait:.1f}s")
        await asyncio.sleep(wait)

    # ---- Output ----

    def add_product(self, product: ScrapedProduct) -> None:
        self._products.append(product)

    def _save_results(self) -> None:
        """Guarda productos y respuestas XHR crudas para debug."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        products_file = OUTPUT_DIR / f"{self.store_id}_{timestamp}.jsonl"
        with products_file.open("w", encoding="utf-8") as f:
            for p in self._products:
                f.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
        logger.info(f"[{self.store_id}] Productos guardados en {products_file}")

        # El debug de XHR es oro puro cuando un selector rompe
        if self._captured_responses:
            xhr_file = OUTPUT_DIR / f"{self.store_id}_{timestamp}_xhr.json"
            with xhr_file.open("w", encoding="utf-8") as f:
                json.dump(self._captured_responses, f, ensure_ascii=False, indent=2)
            logger.debug(f"[{self.store_id}] XHR debug: {xhr_file}")

        self._prune_output_files(f"{self.store_id}_*.jsonl", keep_last=OUTPUT_KEEP_LAST)
        self._prune_output_files(f"{self.store_id}_*_xhr.json", keep_last=OUTPUT_KEEP_LAST)

    def _prune_output_files(self, pattern: str, keep_last: int = 3) -> None:
        """Mantiene solo los archivos más recientes para evitar saturar data/raw."""
        if keep_last <= 0:
            return

        files = sorted(
            OUTPUT_DIR.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        stale = files[keep_last:]
        for file_path in stale:
            try:
                file_path.unlink()
                logger.debug(f"[{self.store_id}] Eliminado archivo antiguo: {file_path.name}")
            except Exception as e:
                logger.warning(f"[{self.store_id}] No se pudo eliminar {file_path.name}: {e}")

    # ---- Subclase implementa ----

    @abstractmethod
    async def scrape(self, page: Page) -> None:
        """Lógica específica por tienda. Debe llamar self.add_product()."""
        ...

    # ---- Helpers comunes ----

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def goto_with_retry(self, page: Page, url: str) -> None:
        """Navegación con reintentos: sitios grandes a veces devuelven 503."""
        logger.info(f"[{self.store_id}] GET {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    @staticmethod
    def parse_cop_price(raw: str | float | int | None) -> float | None:
        """Convierte '$ 45.900' o '45.900,00' a float 45900.0.

        En Colombia el punto es separador de miles y la coma decimal.
        """
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        s = str(raw).strip()
        # Remover símbolos de moneda y espacios
        s = s.replace("$", "").replace("COP", "").replace("\xa0", "").strip()
        # Si tiene coma decimal, quitar puntos de miles y convertir coma a punto
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            # Sin coma, puntos son separadores de miles
            s = s.replace(".", "")
        try:
            return float(s)
        except ValueError:
            logger.warning(f"No se pudo parsear precio: {raw!r}")
            return None

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

    def _absolute_url(self, href: str | None) -> str | None:
        if not href:
            return None
        if href.startswith("http"):
            return href
        return f"{self.base_url}{href}"
