# Actualizar datos en LicorScan sin VM

Mientras no tengas la VM desplegada, puedes actualizar los datos manualmente en Supabase de varias formas:

## Opción 1: Script Manual Local (Recomendado)

Ejecuta el script en tu máquina local:

```bash
# Actualizar exito, carulla, olimpica
python scripts/manual_update_supabase.py --stores exito carulla olimpica

# Actualizar todas las tiendas
python scripts/manual_update_supabase.py --stores all

# Solo reconstruir catálogo y subir (sin scraping)
python scripts/manual_update_supabase.py --skip-scrape
```

**Qué hace:**
1. Ejecuta scrapers de las tiendas seleccionadas
2. Genera `frontend/catalog-data.js`
3. Sube datos a Supabase via REST API
4. Te muestra instrucciones para commit + push

**Tiempo:** ~5-10 minutos por tienda

---

## Opción 2: Cargar datos directamente en Supabase (Sin scraping)

Si ya tienes productos en `data/raw/`, puedes cargar solo desde el archivo:

```bash
python scripts/upload_to_supabase.py
```

---

## Opción 3: Frontend en vivo desde Supabase

Cambiar a la versión que lee datos en vivo desde Supabase (en lugar de archivo estático):

### En Vercel:

1. En tu dashboard de Vercel, abre el proyecto
2. Ve a **Settings → Environment Variables**
3. Asegúrate de que estas variables existan:
   - `REACT_APP_SUPABASE_URL` = `https://bwxxifwqnkrfbegoycod.supabase.co`
   - `REACT_APP_SUPABASE_ANON` = `sb_publishable_...` (tu clave pública)

4. En tu repositorio local, renombra o reemplaza el frontend:

```bash
# Opción A: Usar la versión con Supabase
cp frontend/index-supabase.html frontend/index.html

# Opción B: Mantener ambas versiones
# frontend/index.html → versión estática
# frontend/index-supabase.html → versión con Supabase en vivo
```

5. Commit y push:

```bash
git add frontend/
git commit -m "Switch to live Supabase frontend"
git push origin main
```

6. Vercel automáticamente redeploya en 1-2 minutos

---

## Indicador de Datos

El frontend muestra un badge en la esquina superior:

- 🔴 **Datos en vivo** = Conectado a Supabase y actualizado
- 💾 **Datos cacheados** = Usando `catalog-data.js` (fallback si Supabase no responde)

---

## Cuándo usar cada opción

| Escenario | Opción |
|-----------|--------|
| Necesito actualizar TODO (scrape + subir) | 1: Script Manual |
| Ya tengo datos scraped, solo quiero subir | 2: Upload directo |
| Quiero datos en vivo siempre | 3: Frontend Supabase |
| Prefiero datos cacheados (más rápido) | Mantener versión actual |

---

## Próximo paso: VM Backend Automation

Una vez que tengas los datos en Supabase, el siguiente paso es desplegar la VM con systemd para automatizar esto:

```bash
# Ver instrucciones en:
cat BACKEND_VM_SETUP.md
```

Esto reemplaza el paso manual con una tarea que corre automáticamente cada día a las 02:00 GMT-5.

---

## Troubleshooting

**"Supabase fetch failed"**: El frontend sigue usando datos cacheados (fallback). Verifica que las variables de entorno estén correctas en Vercel.

**"No credentials in .env"**: Copiar `.env.example` a `.env` y rellenar `SUPABASE_URL` y `SUPABASE_KEY`.

**"Upload timed out"**: Aumentar timeout en `scripts/upload_to_supabase.py` o dividir scraping en batches más pequeños.
