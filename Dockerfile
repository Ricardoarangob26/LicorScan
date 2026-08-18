# Imagen de la API. El scraper no va aquí: corre como job aparte, y
# meter Playwright/Chromium en esta imagen la haría varias veces más
# grande sin que la API lo use nunca.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg2-binary trae sus wheels, así que no hacen falta compiladores.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY apiserver/ ./apiserver/
COPY core/ ./core/

# Usuario sin privilegios.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status==200 else 1)"

# Azure App Service inyecta el puerto en $PORT; 8000 en local.
CMD ["sh", "-c", "uvicorn apiserver.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
