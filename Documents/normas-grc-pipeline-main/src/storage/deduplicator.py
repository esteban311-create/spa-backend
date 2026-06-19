"""
src/storage/deduplicator.py — Normalización y deduplicación de normas.

Normaliza variantes ortográficas y elimina duplicados
por URL y por hash de contenido.
"""
import re
import pandas as pd
import config
from utils.logger import get_logger

log = get_logger("deduplicator")

# ── Reglas de normalización de tipo_norma ──────────────────────────
TIPO_NORMA_MAP = {
    r"circular\s*externa": "Circulares",
    r"carta\s*circular":   "Circulares",
    r"circular":            "Circulares",
    r"resoluci[oó]n":       "Resolución",
    r"decreto":             "Decreto",
    r"acuerdo":             "Acuerdos",
    r"ley\b":               "Ley",
    r"reglamento":          "Reglamentos",
}


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza valores de tipo_norma y autoridad."""
    df = df.copy()

    def _norm_tipo(valor: str) -> str:
        v = (valor or "").strip().lower()
        for pattern, canonical in TIPO_NORMA_MAP.items():
            if re.search(pattern, v, re.I):
                return canonical
        return valor.title() if valor else "Circulares"

    antes = df["tipo_norma"].tolist()
    df["tipo_norma"] = df["tipo_norma"].apply(_norm_tipo)
    cambios = sum(1 for a, b in zip(antes, df["tipo_norma"]) if a != b)
    if cambios:
        log.info(f"Normalizados {cambios} valores de tipo_norma")

    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina registros duplicados por URL y por hash de contenido."""
    inicial = len(df)

    # Duplicados por URL
    df = df.drop_duplicates(subset=["url"], keep="first")
    por_url = inicial - len(df)

    # Duplicados por hash de contenido (mismo texto, distinta URL)
    df = df.drop_duplicates(subset=["hash_contenido"], keep="first")
    por_hash = inicial - por_url - len(df)

    if por_url or por_hash:
        log.info(
            f"Duplicados eliminados: {por_url} por URL, "
            f"{por_hash} por hash — quedan {len(df)}"
        )
    return df.reset_index(drop=True)
