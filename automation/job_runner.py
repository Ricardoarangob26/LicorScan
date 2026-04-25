from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger


BASE_DIR = Path(__file__).resolve().parent.parent
STATUS_DIR = BASE_DIR / "data" / "cache"
STATUS_FILE = STATUS_DIR / "cache_status.json"

DEFAULT_STORES = ["exito", "d1", "carulla", "olimpica"]


@dataclass
class JobState:
    store: str
    interval_minutes: int
    last_run_at: datetime | None = None

    def due(self, now: datetime) -> bool:
        if self.last_run_at is None:
            return True
        return (now - self.last_run_at) >= timedelta(minutes=self.interval_minutes)


def parse_args() -> argparse.Namespace:
    default_interval = int(os.getenv("JOB_INTERVAL_MINUTES", "180"))
    default_cache_ttl = int(os.getenv("CACHE_TTL_MINUTES", "30"))
    default_loop_sleep = int(os.getenv("JOB_LOOP_SLEEP_SECONDS", "45"))

    parser = argparse.ArgumentParser(description="Scheduler automático de scrapers y caché")
    parser.add_argument("--stores", nargs="*", default=DEFAULT_STORES, help="Tiendas a ejecutar")
    parser.add_argument("--interval-minutes", type=int, default=default_interval, help="Frecuencia por tienda en minutos")
    parser.add_argument("--cache-ttl-minutes", type=int, default=default_cache_ttl, help="TTL lógico del caché para metadata")
    parser.add_argument("--loop-sleep-seconds", type=int, default=default_loop_sleep, help="Pausa entre ciclos del scheduler")
    parser.add_argument("--run-once", action="store_true", help="Ejecuta un solo ciclo y termina")
    parser.add_argument("--verbose", "-v", action="store_true", help="Logs DEBUG")
    return parser.parse_args()


def run_store_scraper(store: str) -> bool:
    cmd = [sys.executable, "-m", "scraper.main", "--store", store]
    logger.info(f"[job] Ejecutando {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=BASE_DIR, check=False)
    if completed.returncode != 0:
        logger.error(f"[job] Fallo scraping {store} (exit={completed.returncode})")
        return False
    logger.success(f"[job] Scraping OK para {store}")
    return True


def refresh_front_cache() -> bool:
    cmd = [sys.executable, "build_front_catalog.py"]
    logger.info(f"[job] Refrescando cache frontend: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=BASE_DIR, check=False)
    if completed.returncode != 0:
        logger.error(f"[job] Fallo al refrescar cache frontend (exit={completed.returncode})")
        return False
    logger.success("[job] Cache frontend actualizado")
    return True


def write_status(
    states: list[JobState],
    cache_ttl_minutes: int,
    refreshed: bool,
    cycle_started_at: datetime,
) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    next_refresh_at = datetime.now(timezone.utc) + timedelta(minutes=cache_ttl_minutes)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cache": {
            "path": "frontend/catalog-data.js",
            "source": "raw_jsonl",
            "notes": "Preparado para cambiar a origen BD en una fase posterior.",
            "ttl_minutes": cache_ttl_minutes,
            "next_refresh_at": next_refresh_at.isoformat(),
            "refreshed_this_cycle": refreshed,
        },
        "jobs": [
            {
                "store": state.store,
                "interval_minutes": state.interval_minutes,
                "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
                "next_run_at": (
                    (state.last_run_at + timedelta(minutes=state.interval_minutes)).isoformat()
                    if state.last_run_at
                    else cycle_started_at.isoformat()
                ),
            }
            for state in states
        ],
    }
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[job] Estado escrito en {STATUS_FILE}")


def run_cycle(states: list[JobState], cache_ttl_minutes: int) -> None:
    now = datetime.now(timezone.utc)
    touched_store = False
    for state in states:
        if not state.due(now):
            continue
        ok = run_store_scraper(state.store)
        if ok:
            state.last_run_at = datetime.now(timezone.utc)
            touched_store = True

    refreshed = False
    if touched_store:
        refreshed = refresh_front_cache()

    write_status(states=states, cache_ttl_minutes=cache_ttl_minutes, refreshed=refreshed, cycle_started_at=now)


def main() -> None:
    args = parse_args()

    logger.remove()
    level = "DEBUG" if args.verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> <level>{level: <8}</level> {message}")

    states = [JobState(store=store, interval_minutes=args.interval_minutes) for store in args.stores]

    logger.info("[job] Scheduler iniciado")
    logger.info(f"[job] Tiendas: {', '.join(args.stores)}")
    logger.info(f"[job] Intervalo por tienda: {args.interval_minutes} minutos")

    if args.run_once:
        run_cycle(states, args.cache_ttl_minutes)
        logger.success("[job] Ciclo unico completado")
        return

    while True:
        run_cycle(states, args.cache_ttl_minutes)
        time.sleep(args.loop_sleep_seconds)


if __name__ == "__main__":
    main()
