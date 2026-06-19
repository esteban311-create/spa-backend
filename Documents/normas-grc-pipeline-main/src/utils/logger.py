"""
utils/logger.py — Logger global del pipeline, basado en loguru.

Uso en cualquier módulo:
    from utils.logger import get_logger
    log = get_logger("sfc_scraper")
    log.info("Procesando norma {}", nombre)

Salidas:
  - Consola (nivel configurable con LOG_LEVEL en .env).
  - Archivo logs/pipeline_YYYYMMDD.log con rotación diaria.
"""
import sys
from loguru import logger
import config

config.ensure_dirs()

logger.configure(extra={"module": "pipeline"})
logger.remove()

logger.add(
    sys.stderr,
    level=config.LOG_LEVEL,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[module]}</cyan> | "
        "{message}"
    ),
)

logger.add(
    config.LOGS_DIR / "pipeline_{time:YYYYMMDD}.log",
    level="DEBUG",
    rotation="00:00",
    retention=config.LOG_RETENTION,
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[module]} | {message}",
)


def get_logger(module: str):
    """Devuelve un logger con el campo module enlazado al nombre dado."""
    return logger.bind(module=module)
