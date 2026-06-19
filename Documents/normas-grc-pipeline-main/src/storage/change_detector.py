"""
src/storage/change_detector.py — Detección de normas nuevas o modificadas.

Compara el hash_contenido de la corrida actual contra la anterior.
Solo las normas con estado_cambio = nuevo | modificado pasan al pipeline NLP.
"""
import pandas as pd
import config
from utils.logger import get_logger

log = get_logger("change_detector")

ESTADO_NUEVO      = "nuevo"
ESTADO_MODIFICADO = "modificado"
ESTADO_SIN_CAMBIO = "sin_cambio"


def detect(df_nuevo: pd.DataFrame, df_prev: pd.DataFrame) -> pd.DataFrame:
    """
    Añade la columna 'estado_cambio' al DataFrame de normas nuevas.

    Args:
        df_nuevo: DataFrame de la corrida actual (schema raw).
        df_prev:  DataFrame de la corrida anterior (puede estar vacío).

    Returns:
        df_nuevo con columna estado_cambio agregada.
    """
    if df_prev.empty:
        log.info("Sin corrida anterior — todas las normas marcadas como 'nuevo'")
        df_nuevo = df_nuevo.copy()
        df_nuevo["estado_cambio"] = ESTADO_NUEVO
        return df_nuevo

    # Índice por id_externo para comparación rápida
    prev_idx = df_prev.set_index("id_externo")["hash_contenido"].to_dict()

    def _estado(row):
        id_ext = row["id_externo"]
        if id_ext not in prev_idx:
            return ESTADO_NUEVO
        if row["hash_contenido"] != prev_idx[id_ext]:
            return ESTADO_MODIFICADO
        return ESTADO_SIN_CAMBIO

    df_resultado = df_nuevo.copy()
    df_resultado["estado_cambio"] = df_resultado.apply(_estado, axis=1)

    nuevas   = (df_resultado["estado_cambio"] == ESTADO_NUEVO).sum()
    modif    = (df_resultado["estado_cambio"] == ESTADO_MODIFICADO).sum()
    sin_camp = (df_resultado["estado_cambio"] == ESTADO_SIN_CAMBIO).sum()

    log.info(
        f"Detección de cambios: {nuevas} nuevas, "
        f"{modif} modificadas, {sin_camp} sin cambio"
    )
    return df_resultado
