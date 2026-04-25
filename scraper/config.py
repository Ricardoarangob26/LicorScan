"""Configuración central del scraper.

Centraliza delays, User-Agents y rutas según el DTD.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Rutas
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Modo navegador
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

# Pool de User-Agents realistas (Chrome/Firefox desktop recientes).
# La rotación evita el patrón de "siempre mismo UA" que marca sitios como bot.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
]

# Config por tienda (matching tabla 2.2.3 del DTD)
STORES = {
    "exito": {
        "name": "Éxito",
        "base_url": "https://www.exito.com",
        "categories": {
            # Categorías validadas en sitio real para ampliar cobertura.
            "licores": "/vinos-y-licores",
            "bebidas": "/mercado/bebidas",
            "snacks": "/mercado/pasabocas-y-snacks",
        },
        "delay_seconds": int(os.getenv("EXITO_DELAY", 12)),
        "max_rph": 300,
    },
    "d1": {
        "name": "D1",
        "base_url": "https://domicilios.tiendasd1.com",
        "categories": {
            "licores": "/ca/bebidas/licores/BEBIDAS/LICORES",
            "vinos": "/ca/bebidas/vinos/BEBIDAS/VINOS",
            "bebidas": "/ca/bebidas/BEBIDAS",
            "snacks": "https://domicilios.tiendasd1.com/ca/alimentos%20y%20despensa/ALIMENTOS%20Y%20DESPENSA?categories=Pasabocas+y+snacks",
            "dulceria": "https://domicilios.tiendasd1.com/ca/alimentos%20y%20despensa/dulceria/ALIMENTOS%20Y%20DESPENSA/DULCER%C3%8DA",
        },
        "delay_seconds": int(os.getenv("D1_DELAY", 8)),
        "max_rph": 450,
    },
    "carulla": {
        "name": "Carulla",
        "base_url": "https://www.carulla.com",
        "categories": {
            "licores": "/vinos-y-licores",
            "bebidas": "/bebidas-snacks-y-dulces",
            "cocteles": "/vinos-y-licores/cocteles-y-bases?category-1=vinos-y-licores&category-2=cocteles-y-bases&facets=category-1%2Ccategory-2&sort=discount_desc&page=0",
        },
        "delay_seconds": int(os.getenv("CARULLA_DELAY", 12)),
        "max_rph": 300,
    },
    "olimpica": {
        "name": "Olímpica",
        "base_url": "https://www.olimpica.com",
        "categories": {
            "licores": "/supermercado/licores",
        },
        "delay_seconds": int(os.getenv("OLIMPICA_DELAY", 8)),
        "max_rph": 450,
    },
    # Los demás se llenan cuando se implementen
}

# Selectores y endpoints detectados dinámicamente durante desarrollo.
# Se llenan a medida que se inspeccione cada sitio con DevTools.
MAX_PRODUCTS_PER_CATEGORY = int(os.getenv("MAX_PRODUCTS_PER_CATEGORY", 0))
MAX_PAGES_PER_CATEGORY = int(os.getenv("MAX_PAGES_PER_CATEGORY", 35))
OUTPUT_KEEP_LAST = int(os.getenv("OUTPUT_KEEP_LAST", 3))
