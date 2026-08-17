"""Ingesta: del adaptador a la base de datos.

    py -m core.ingest --discover exito        # ver el árbol de categorías
    py -m core.ingest --store d1              # ingesta de una tienda
    py -m core.ingest --all                   # las cuatro
    py -m core.ingest --store d1 --dry-run    # sin escribir en la BD

Cada corrida queda registrada en `scrape_runs`, de modo que un adaptador
roto se ve en la base y no solo en los logs.
"""
from __future__ import annotations

import argparse
import sys
import time

from loguru import logger

from core.adapters import get_adapter
from core.db import Repository, connect
from core.identity import resolve
from core.models import StoreConfig
from core.stores import STORES, get_store


def discover(config: StoreConfig, depth: int = 3) -> None:
    adapter = get_adapter(config.platform)(config)
    tree = adapter.discover_categories(depth=depth)
    logger.info(f"[{config.slug}] {len(tree)} categorías raíz")
    for node in tree:
        print(f"  {node.get('id'):>10}  {node.get('name')}")
        for child in node.get("children") or []:
            print(f"  {child.get('id'):>10}      - {child.get('name')}")


def _write_batch_with_retry(store_id: int, run_id: int, batch: list, stats: dict,
                            attempts: int = 6) -> bool:
    """Reintenta el lote ante fallos transitorios de red.

    Una ingesta completa tarda decenas de minutos y una caída puntual de
    DNS o de la conexión no debería tirar toda la corrida: se espera y se
    reintenta el lote, que es idempotente (upsert por (store_id, sku)).
    El único efecto de repetir es una fila extra en `prices`, que al ser
    append-only es una observación más, no un dato corrupto.
    """
    for attempt in range(1, attempts + 1):
        try:
            _write_batch(store_id, run_id, batch, stats)
            return True
        except Exception as exc:
            if attempt == attempts:
                logger.error(f"lote descartado tras {attempts} intentos: {exc!r}")
                stats["errors"] += len(batch)
                return False
            # Espera creciente: un corte de red puede durar varios
            # minutos, y esperar sale más barato que perder la corrida.
            wait = min(30 * attempt, 180)
            logger.warning(f"fallo de red en el lote ({exc!r}); reintento {attempt}/{attempts - 1} en {wait}s")
            time.sleep(wait)
    return False


def _write_batch(store_id: int, run_id: int, batch: list, stats: dict) -> None:
    """Persiste un lote con su propia conexión, de vida corta."""
    with connect() as conn:
        repo = Repository(conn)
        for product in batch:
            try:
                sp_id, is_new = repo.upsert_store_product(store_id, product)
                if is_new:
                    stats["products_new"] += 1

                match = resolve(conn, repo, product)
                repo.link_product(
                    sp_id, match.product_id, match.method,
                    match.confidence, match.needs_review,
                )
                if match.needs_review:
                    stats["needs_review"] += 1
                else:
                    stats["matched"] += 1

                repo.insert_price(sp_id, product, run_id)
                stats["prices_written"] += 1
                conn.commit()
            except Exception as exc:
                conn.rollback()
                stats["errors"] += 1
                logger.error(f"fallo con sku={product.sku}: {exc!r}")


def ingest_store(config: StoreConfig, dry_run: bool = False, batch_size: int = 100) -> dict:
    adapter = get_adapter(config.platform)(config)
    stats = {"products_found": 0, "products_new": 0, "prices_written": 0,
             "errors": 0, "matched": 0, "needs_review": 0}

    if dry_run:
        for _ in adapter.fetch_products():
            stats["products_found"] += 1
        logger.info(f"[{config.slug}] dry-run: {stats['products_found']} productos")
        return stats

    # Conexión breve solo para abrir la corrida.
    with connect() as conn:
        repo = Repository(conn)
        store_id = repo.upsert_store(config)
        run_id = repo.start_run(store_id, adapter.platform)
        conn.commit()
    logger.info(f"[{config.slug}] corrida #{run_id} iniciada")

    status = "completed"
    notes: str | None = None
    batch: list = []
    try:
        for product in adapter.fetch_products():
            stats["products_found"] += 1
            batch.append(product)
            if len(batch) >= batch_size:
                _write_batch_with_retry(store_id, run_id, batch, stats)
                batch = []
                logger.info(f"[{config.slug}] {stats['products_found']} procesados…")
        if batch:
            _write_batch_with_retry(store_id, run_id, batch, stats)
    except Exception as exc:
        status = "failed"
        notes = repr(exc)[:400]
        stats["errors"] += 1
        logger.error(f"[{config.slug}] corrida interrumpida: {exc!r}")

    # Cerrar la corrida siempre, incluso si algo falló: una corrida que
    # queda en 'running' para siempre es peor que una marcada 'failed'.
    try:
        with connect() as conn:
            Repository(conn).finish_run(run_id, status, notes=notes, **stats)
            conn.commit()
    except Exception as exc:
        logger.error(f"[{config.slug}] no se pudo cerrar la corrida #{run_id}: {exc!r}")

    logger.success(
        f"[{config.slug}] {stats['products_found']} productos · "
        f"{stats['products_new']} nuevos · {stats['prices_written']} precios · "
        f"{stats['matched']} con identidad · {stats['needs_review']} para revisar · "
        f"{stats['errors']} errores"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de catálogo a la base de datos")
    parser.add_argument("--store", help="Slug de la tienda")
    parser.add_argument("--all", action="store_true", help="Todas las tiendas configuradas")
    parser.add_argument("--discover", help="Mostrar el árbol de categorías de una tienda")
    parser.add_argument("--dry-run", action="store_true", help="No escribir en la base")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "INFO",
               format="<green>{time:HH:mm:ss}</green> <level>{level: <8}</level> {message}")

    if args.discover:
        discover(get_store(args.discover))
        return

    if args.all:
        targets = list(STORES.values())
    elif args.store:
        targets = [get_store(args.store)]
    else:
        parser.error("Indica --store, --all o --discover")

    totals = {"products_found": 0, "prices_written": 0, "needs_review": 0, "errors": 0}
    for config in targets:
        try:
            stats = ingest_store(config, dry_run=args.dry_run)
            for key in totals:
                totals[key] += stats.get(key, 0)
        except Exception as exc:
            logger.error(f"[{config.slug}] corrida abortada: {exc!r}")
            totals["errors"] += 1

    if len(targets) > 1:
        logger.success(
            f"TOTAL · {totals['products_found']} productos · "
            f"{totals['prices_written']} precios · "
            f"{totals['needs_review']} para revisar · {totals['errors']} errores"
        )


if __name__ == "__main__":
    main()
