"""CLI principal del scraper.

Uso:
    python -m scraper.main --store exito
    python -m scraper.main --store exito --headed   # fuerza ver navegador
"""
import argparse
import asyncio
import os
import sys

from loguru import logger

from scraper.spiders import CarullaSpider, D1Spider, ExitoSpider, OlimpicaSpider

SPIDERS = {
    "exito": ExitoSpider,
    "d1": D1Spider,
    "carulla": CarullaSpider,
    "olimpica": OlimpicaSpider,
}


async def run_spider(store: str) -> None:
    spider_cls = SPIDERS.get(store)
    if not spider_cls:
        logger.error(f"Spider '{store}' no existe. Disponibles: {list(SPIDERS)}")
        sys.exit(1)
    spider = spider_cls()
    products = await spider.run()
    logger.success(f"{len(products)} productos extraídos de {store}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LicorScan scraper CLI")
    parser.add_argument("--store", required=True, choices=list(SPIDERS), help="Tienda a scrapear")
    parser.add_argument("--headed", action="store_true", help="Forzar modo con navegador visible")
    parser.add_argument("--verbose", "-v", action="store_true", help="Logs DEBUG")
    args = parser.parse_args()

    # Configurar logging
    logger.remove()
    level = "DEBUG" if args.verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> <level>{level: <8}</level> {message}")

    if args.headed:
        os.environ["HEADLESS"] = "false"

    asyncio.run(run_spider(args.store))


if __name__ == "__main__":
    main()
