# LicorScan Colombia — Scraper

[![Repo](https://img.shields.io/badge/GitHub-Ricardoarangob26%2FLicorScan-181717?logo=github)](https://github.com/Ricardoarangob26/LicorScan)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Frontend](https://img.shields.io/badge/Frontend-React%20CDN-61DAFB?logo=react&logoColor=222)](frontend/index.html)

Comparador de precios de licores y consumibles para fiesta en Colombia.
Este repo contiene la capa de **extracción de datos** (Playwright) del proyecto.

## Estado

- [x] Scrapers funcionales: Éxito, D1, Carulla, Olímpica
- [x] Exportación de catálogo para frontend (`frontend/catalog-data.js`)
- [x] Front local con filtros, comparación y panel de histórico
- [x] Jobs automáticos de scraping + refresh de caché
- [x] Job separado cache-only (preparado para fuente futura en BD)
- [ ] Persistencia en BD (fase siguiente)

## Quickstart (Local)

### 1) Instalar dependencias

```bash
python -m venv venv
# Windows PowerShell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m playwright install chromium
```

### 2) Correr una pasada de scraping

```bash
venv\Scripts\python.exe -m scraper.main --store exito
venv\Scripts\python.exe -m scraper.main --store d1
venv\Scripts\python.exe -m scraper.main --store carulla
venv\Scripts\python.exe -m scraper.main --store olimpica
```

### 3) Generar caché para frontend

```bash
venv\Scripts\python.exe build_front_catalog.py
```

### 4) Levantar frontend local

```bash
venv\Scripts\python.exe -m http.server 5500 --directory frontend
```

Abrir: `http://127.0.0.1:5500/index.html`

## Setup

### 1. Python y dependencias

Requiere Python 3.11+.

```bash
cd licorscan
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Variables de entorno

```bash
cp .env.example .env
# Editar .env si quieres cambiar delays o modo headless
```

Para la primera ejecución contra un sitio nuevo, **deja `HEADLESS=false`**
para poder ver el navegador y abrir DevTools si los selectores fallan.

### 3. Primera corrida (Éxito)

```bash
python -m scraper.main --store exito --headed -v
```

**Qué esperar:**
1. Se abre una ventana de Chromium navegando a exito.com/mercado/licores-y-vinos.
2. Espera ~15s a que cargue el SPA.
3. Hace 3 scrolls para forzar lazy-load.
4. Extrae hasta 20 productos de cada categoría configurada.
5. Guarda resultados en `data/raw/exito_<timestamp>.jsonl`.
6. Guarda respuestas XHR interesantes en `data/raw/exito_<timestamp>_xhr.json`.

### 4. Inspeccionar resultados

```bash
# Ver productos extraídos
head data/raw/exito_*.jsonl

# Ver qué endpoints XHR devolvieron JSON (oro puro para debugging)
jq '.[].url' data/raw/exito_*_xhr.json | sort -u
```

## Workflow cuando un selector rompe

Los sitios SPA cambian su DOM. Cuando `exito_<timestamp>.jsonl` salga vacío o
mal parseado, el flujo es:

1. Correr de nuevo con `--headed` para ver el sitio.
2. Abrir DevTools → Elements, inspeccionar un card de producto.
3. Buscar un atributo estable: `data-testid`, `data-sku`, clase con prefijo `vtex-`.
4. Actualizar los selectores en `scraper/spiders/exito.py`.
5. Si los selectores son frágiles, revisar `data/raw/exito_*_xhr.json`:
   probablemente haya un endpoint JSON interno con los datos estructurados.
   Cambiar la estrategia a parseo del XHR (ver `BaseSpider._on_response`).

## Estructura

```
licorscan/
├── scraper/
│   ├── spiders/
│   │   ├── base.py          # Rate limiting + XHR capture + retries
│   │   └── exito.py         # Spider piloto
│   ├── config.py            # Settings centralizados
│   └── main.py              # CLI
├── data/raw/                # Output JSONL + XHR debug
├── tests/
└── requirements.txt
```

## Tests

```bash
pytest tests/ -v
```

## Automatizacion: jobs + cache

Para no depender de consultas frecuentes a una BD (cuando la agreguemos),
el flujo recomendado es:

1. Jobs de scraping por tienda en background.
2. Refresco de cache de catalogo para frontend/API.
3. Clientes leen cache y no pegan directo al origen de datos.

Este repo ya incluye el scheduler base en [automation/job_runner.py](automation/job_runner.py).

### Ejecucion puntual (1 ciclo)

```bash
python -m automation.job_runner --stores exito d1 carulla olimpica --run-once
```

### Ejecucion continua

```bash
python -m automation.job_runner
```

### Job separado: solo refresco de cache

Refresca el cache sin ejecutar scraping. Esto sirve para el escenario futuro
en el que la fuente principal sea BD.

```bash
python -m automation.cache_refresh --source raw_jsonl
```

Cuando exista export desde BD:

```bash
python -m automation.cache_refresh --source db_json --db-json-path data/derived/db_products_cache.json
```

Variables opcionales en `.env`/`.env.example`:

- `JOB_INTERVAL_MINUTES` frecuencia de scraping por tienda.
- `CACHE_TTL_MINUTES` TTL logico del cache.
- `JOB_LOOP_SLEEP_SECONDS` intervalo de polling del scheduler.
- `CACHE_SOURCE` origen preferido del cache en jobs cache-only.

### Artefactos del pipeline automatico

- Cache para frontend: [frontend/catalog-data.js](frontend/catalog-data.js)
- Estado de jobs/cache: [data/cache/cache_status.json](data/cache/cache_status.json)
- Generador del cache: [build_front_catalog.py](build_front_catalog.py)

### Ruta futura a BD

Cuando agreguemos persistencia (Postgres/Supabase), la idea es mantener
el mismo patron:

1. Scraper escribe en BD.
2. Job de sincronizacion alimenta cache materializado.
3. Front/API sirve desde cache con TTL y refresh automatico.

Asi evitamos alta carga de lectura sobre la BD y mantenemos baja latencia.

## Política de cortesía

Este scraper respeta las políticas de rate limiting del DTD:
- Delays de 8-12s entre requests según tienda.
- Horario objetivo de producción: 02:00–05:00 GMT-5.
- Rotación de User-Agent desde un pool de navegadores realistas.
- Solo se extraen datos públicos (nombre y precio).
