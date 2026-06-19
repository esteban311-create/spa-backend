"""
src/storage/raw_storage.py — Almacenamiento del Excel crudo.

Recibe la lista de normas del scraper_manager y guarda
data/raw/normas_raw_YYYYMMDD.xlsx con el schema RAW fijo.
"""
from datetime import datetime
from pathlib import Path
import pandas as pd
import config
from utils.logger import get_logger

log = get_logger("raw_storage")


def save(normas: list[dict]) -> Path:
    """
    Guarda la lista de normas en un Excel crudo.

    Returns:
        Ruta del archivo generado.
    """
    config.ensure_dirs()

    if not normas:
        log.warning("No hay normas para guardar")
        return None

    df = pd.DataFrame(normas)

    # Garantizar que todas las columnas del schema estén presentes
    for col in config.SCHEMA_RAW:
        if col not in df.columns:
            df[col] = ""
    df = df[config.SCHEMA_RAW]

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = config.RAW_DIR / f"normas_raw_{fecha_str}.xlsx"

    df.to_excel(ruta, index=False, engine="openpyxl")
    log.info(f"Excel crudo guardado: {ruta} ({len(df)} filas)")
    return ruta


def load_latest() -> pd.DataFrame:
    """Carga el Excel crudo más reciente de data/raw/."""
    archivos = sorted(config.RAW_DIR.glob("normas_raw_*.xlsx"), reverse=True)
    if not archivos:
        log.warning("No hay archivos raw. Ejecuta primero el scraper.")
        return pd.DataFrame(columns=config.SCHEMA_RAW)
    log.info(f"Cargando: {archivos[0].name}")
    return pd.read_excel(archivos[0], engine="openpyxl", dtype=str).fillna("")
