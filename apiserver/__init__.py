"""API REST de LicorScan.

Vive en `apiserver/` y no en `api/`, porque esa carpeta la reserva
Vercel para funciones serverless y el frontend estático todavía se
despliega ahí. Esta API corre aparte, en Azure App Service.

La API es agnóstica a la tienda: trabaja con Product, Price, Store,
Brand y Category, y no sabe si el dato vino de Éxito, D1 o de un
adaptador futuro.
"""

__version__ = "1.0.0"
