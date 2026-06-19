"""
src/scraper/scraper_manager.py — Orquestador de scrapers.

Para agregar una nueva fuente:
  1. Importar el scraper
  2. Agregar a SCRAPER_REGISTRY
  3. Activar en config.py (SOURCES['CODIGO']['activo'] = True)
"""
from utils.logger import get_logger
import config

# ─── Registro de scrapers disponibles ────────────────────────────────
# Clave: SOURCE_CODE   Valor: clase del scraper
from sfc_scraper    import SFCScraper
from banrep_scraper import BanRepScraper
from urf_scraper    import URFScraper
from minhac_scraper import MinhacScraper
#from dian_scraper   import DIANScraper

SCRAPER_REGISTRY = {
    "SFC":    SFCScraper,
    "BANREP": BanRepScraper,
    "URF":    URFScraper,
    "MINHAC": MinhacScraper,
    #"DIAN":   DIANScraper,
    # ── Agregar aquí nuevas fuentes: ──────────────────────────────
    # "URF":    URFScraper,
    # "AMV":    AMVScraper,
    # "CONGRESO": CongresoScraper,
}

log = get_logger("scraper_manager")


def run_all(max_docs_per_source: int = 0) -> list[dict]:
    """
    Ejecuta todos los scrapers activos y consolida los resultados.

    Args:
        max_docs_per_source: límite por fuente (0 = sin límite, 5-10 para testing)

    Returns:
        Lista consolidada de dicts con schema raw.
    """
    fuentes_activas = config.fuentes_activas()
    log.info(
        f"Scrapers a ejecutar: {list(fuentes_activas.keys())}"
        + (f" | max_docs={max_docs_per_source}" if max_docs_per_source else "")
    )

    todos = []
    stats = {}

    for codigo, info in fuentes_activas.items():
        if codigo not in SCRAPER_REGISTRY:
            log.warning(f"Fuente activa {codigo} no tiene scraper registrado")
            continue

        log.info(f"\n{'─'*50}")
        log.info(f"Iniciando: {info['nombre']}")

        try:
            scraper = SCRAPER_REGISTRY[codigo]()
            resultados = scraper.run(max_docs=max_docs_per_source)
            todos.extend(resultados)
            stats[codigo] = len(resultados)
            log.info(f"{codigo}: {len(resultados)} normas extraídas")
        except Exception as e:
            log.error(f"{codigo}: Error fatal — {e}")
            stats[codigo] = 0

    log.info(f"\n{'═'*50}")
    log.info(f"TOTAL: {len(todos)} normas de {len(stats)} fuentes")
    for cod, n in stats.items():
        log.info(f"  {cod}: {n}")

    return todos
