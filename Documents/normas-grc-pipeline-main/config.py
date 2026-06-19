"""
config.py — Configuración centralizada del pipeline de extracción de normas.

Stack NLP 100 % local (sin API externas):
  - Resumen          : sumy (LexRank / LSA) — extractivo, sin red neuronal
  - Clasificación    : reglas keyword + sentence-transformers (MiniLM multilingual)
  - Obligaciones     : spaCy + es_core_news_sm + patrones regex legales

Los modelos se descargan UNA SOLA VEZ en la primera ejecución y quedan en caché
local. A partir de entonces el pipeline funciona sin internet.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ── SSL ────────────────────────────────────────────────────────────
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() not in ("false", "0", "no")

# ── Selenium / Edge ────────────────────────────────────────────────
EDGE_DRIVER_PATH = os.getenv(
    "EDGE_DRIVER_PATH",
    rf"C:\Users\{os.getlogin()}\Documents\edgedriver_win64\msedgedriver.exe"
)

# ─── Carga de .env junto a este archivo ──────────────────────
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


# ═══════════════════════════════════════════════════════════
#  RUTAS
# ═══════════════════════════════════════════════════════════
DATA_DIR       = Path(os.getenv("DATA_PATH", str(BASE_DIR / "data")))
RAW_DIR        = DATA_DIR / "raw"
ENRICHED_DIR   = DATA_DIR / "enriched"
LZ_OUTPUT_DIR  = DATA_DIR / "lz_output"
LOGS_DIR       = BASE_DIR / "logs"

ALL_DIRS = [DATA_DIR, RAW_DIR, ENRICHED_DIR, LZ_OUTPUT_DIR, LOGS_DIR]

def ensure_dirs():
    """Crea todas las carpetas de datos y logs si no existen."""
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════
LOG_LEVEL     = os.getenv("LOG_LEVEL", "INFO")
LOG_RETENTION = os.getenv("LOG_RETENTION", "30 days")


# ═══════════════════════════════════════════════════════════
#  SCRAPING
# ═══════════════════════════════════════════════════════════
SCRAPER_DELAY_SECONDS = float(os.getenv("SCRAPER_DELAY_SECONDS", "2"))
MAX_RETRIES           = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT       = int(os.getenv("REQUEST_TIMEOUT", "30"))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (compatible; NormasBot/1.0; cumplimiento-regulatorio)",
)


# ═══════════════════════════════════════════════════════════
#  NLP — RESUMEN (sumy)
# ═══════════════════════════════════════════════════════════
# Algoritmo de resumen extractivo.
# LexRank → mejor calidad general (basado en grafos de similitud).
# LSA     → más rápido, adecuado para textos muy largos.
SUMY_ALGORITHM      = os.getenv("SUMY_ALGORITHM", "LexRank")
SUMY_SENTENCES_COUNT = int(os.getenv("SUMY_SENTENCES_COUNT", "10"))
SUMY_LANGUAGE       = "spanish"


# ═══════════════════════════════════════════════════════════
#  NLP — CLASIFICACIÓN POR COMPAÑÍA
# ═══════════════════════════════════════════════════════════
# Modelo de embeddings multilingüe (420 MB, descarga automática la 1ª vez).
# Caché en: ~/.cache/huggingface/sentence_transformers/
SENTENCE_TRANSFORMER_MODEL = os.getenv(
    "SENTENCE_TRANSFORMER_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

# Umbral de confianza: debajo → pendiente_validacion = True
CONFIANZA_MIN = float(os.getenv("CONFIANZA_MIN", "0.65"))

# ── Capa 1: reglas keyword deterministas ──────────────────
# Si el texto contiene alguno de estos términos → se asigna esa compañía
# con confianza 0.90 y no se pasa a la capa de embeddings.
KEYWORD_RULES: dict[str, list[str]] = {
    "Bancolombia": [
        "encaje bancario", "cartera de crédito", "captación de depósitos",
        "cuenta corriente", "cuenta de ahorros", "crédito hipotecario",
        "microcrédito", "leasing habitacional", "establecimiento de crédito",
        "sistema de pagos", "acuerdo de basilea", "coeficiente de solvencia",
        "provisiones de cartera", "reforma tributaria", "impuesto de renta",
    ],
    "Fiduciaria": [
        "fiducia mercantil", "fideicomiso", "fondo de inversión colectiva",
        " fic ", "encargo fiduciario", "patrimonio autónomo",
        "administración de recursos de terceros", "fondo de pensiones voluntarias",
        "sociedad fiduciaria", "negocio fiduciario",
    ],
    "Valores": [
        "mercado de valores", "comisionista de bolsa", "bolsa de valores de colombia",
        "titularización", "securitización", "intermediación de valores",
        "autorregulador del mercado de valores", "amv", "custodia de valores",
        "portafolio de inversiones", "sociedad comisionista", "oferta pública",
        "prospecto de emisión", "acciones en bolsa",
    ],
    "Banca de Inversiones": [
        "banca de inversión", "fusión y adquisición", "m&a",
        "asesoría financiera corporativa", "estructuración de deuda",
        "underwriting", "project finance", "sindicación de créditos",
        "capital privado", "private equity",
    ],
}

# ── Capa 2: textos semilla para embeddings ────────────────
# sentence-transformers calcula similitud entre el texto de la norma
# y cada texto semilla; asigna la compañía de mayor similitud.
COMPANY_SEED_TEXTS: dict[str, str] = {
    "Bancolombia": (
        "normas que regulan operaciones de crédito, captación de depósitos, "
        "encaje bancario, solvencia y establecimientos de crédito en Colombia"
    ),
    "Fiduciaria": (
        "normas que regulan fondos de inversión colectiva, fideicomisos, "
        "encargos fiduciarios, patrimonios autónomos y sociedades fiduciarias"
    ),
    "Valores": (
        "normas que regulan el mercado de valores, comisionistas de bolsa, "
        "intermediación bursátil, custodia de valores y la bolsa de Colombia"
    ),
    "Banca de Inversiones": (
        "normas que regulan la banca de inversión, fusiones y adquisiciones, "
        "asesoría financiera corporativa y estructuración de capital"
    ),
}


# ═══════════════════════════════════════════════════════════
#  NLP — EXTRACCIÓN DE OBLIGACIONES (spaCy + regex)
# ═══════════════════════════════════════════════════════════
SPACY_MODEL = os.getenv("SPACY_MODEL", "es_core_news_sm")

# Patrones regex que señalan el inicio de una obligación legal.
# Una oración que contenga alguno de estos marcadores se candidata
# como obligación. Ordenados de más a menos específico.
OBLIGATION_MARKERS: list[str] = [
    r"deberá",
    r"deberán",
    r"debe",
    r"deben",
    r"está obligado",
    r"están obligados",
    r"queda obligado",
    r"se prohíbe",
    r"queda prohibido",
    r"en ningún caso",
    r"es obligatorio",
    r"será obligatorio",
    r"se exige",
    r"es requisito",
    r"dentro del plazo de",
    r"en un plazo no mayor",
    r"so pena de",
    r"bajo pena de",
]

# Número máximo de obligaciones a extraer por norma
MAX_OBLIGACIONES_POR_NORMA = 500


# ═══════════════════════════════════════════════════════════
#  FUENTES REGULATORIAS
# ═══════════════════════════════════════════════════════════
SOURCES: dict[str, dict] = {
    "SFC": {
        "nombre": "Superintendencia Financiera de Colombia",
        "url_base": "https://www.superfinanciera.gov.co",
        "url_index": "",          # TODO Fase 2
        "tipo_contenido": "mixto",
        "activo": True,
    },
    "BANREP": {
        "nombre": "Banco de la República",
        "url_base": "https://www.banrep.gov.co",
        "url_index": "",
        "tipo_contenido": "mixto",
        "activo": True,
    },
    "MINHAC": {
        "nombre": "Ministerio de Hacienda y Crédito Público",
        "url_base": "https://www.minhacienda.gov.co",
        "url_index": "",
        "tipo_contenido": "mixto",
        "activo": True,
    },
    "DIAN": {
        "nombre": "Dirección de Impuestos y Aduanas Nacionales",
        "url_base": "https://www.dian.gov.co",
        "url_index": "",
        "tipo_contenido": "mixto",
        "activo": True,
    },
    "URF": {
        "nombre": "Unidad de Regulación Financiera",
        "url_base": "https://www.urf.gov.co",
        "url_index": "",
        "tipo_contenido": "mixto",
        "activo": True,
    },
    "CONGRESO": {
        "nombre": "Congreso de la República",
        "url_base": "http://www.secretariasenado.gov.co",
        "url_index": "",
        "tipo_contenido": "html",
        "activo": False,
    },
    "AMV": {
        "nombre": "Autorregulador del Mercado de Valores",
        "url_base": "https://www.amvcolombia.org.co",
        "url_index": "",
        "tipo_contenido": "html",
        "activo": False,
    },
    "SUPERSOC": {
        "nombre": "Superintendencia de Sociedades",
        "url_base": "https://www.supersociedades.gov.co",
        "url_index": "",
        "tipo_contenido": "mixto",
        "activo": False,
    },
}

def fuentes_activas() -> dict:
    """Devuelve solo las fuentes marcadas como activas."""
    return {k: v for k, v in SOURCES.items() if v.get("activo")}


# ═══════════════════════════════════════════════════════════
#  CATÁLOGOS DEL NEGOCIO
# ═══════════════════════════════════════════════════════════
COMPANIAS: list[str] = [
    "Bancolombia", "Fiduciaria", "Valores", "Banca de Inversiones"
]

TIPOS_NORMA: list[str] = [
    "Constitución", "Ley", "Decreto", "Acuerdos",
    "Reglamentos", "Resolución", "Circulares",
]


# ═══════════════════════════════════════════════════════════
#  SCHEMA DE LA LANDING ZONE (consistente con HU-NOR-008)
# ═══════════════════════════════════════════════════════════
SCHEMA_LZ_NORMA: list[str] = [
    "id_externo_lz", "fuente", "nombre", "tipo_norma",
    "autoridad_emite", "autoridad_vigila", "fecha_expedicion",
    "fecha_extraccion", "descripcion_nlp", "url", "texto_original",
    "origen_creacion", "estado_clasificacion",
    "confianza_clasificacion", "pendiente_validacion",
]

SCHEMA_LZ_NORMA_COMPANIA: list[str] = [
    "id_externo_lz", "compania", "es_principal"
]

SCHEMA_LZ_OBLIGACION: list[str] = [
    "id_externo_lz_norma", "numeral", "fecha_entrada",
    "texto_obligacion", "confianza_extraccion",
]

SCHEMA_RAW: list[str] = [
    "id_externo", "fuente", "nombre", "tipo_norma", "autoridad",
    "fecha_expedicion", "fecha_extraccion", "url",
    "texto_completo", "hash_contenido",
]


# ═══════════════════════════════════════════════════════════
#  LÍMITES (consistentes con las HUs)
# ═══════════════════════════════════════════════════════════
MAX_NOMBRE              = 200
MAX_DESCRIPCION         = 5000
MAX_TEXTO_OBLIGACION    = 5000
MAX_URL                 = 500
MAX_NUMERAL             = 10
