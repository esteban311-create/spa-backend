"""
src/scraper/base_scraper.py — Clase abstracta para todos los scrapers.

Para agregar una nueva fuente regulatoria:
  1. Crear src/scraper/NOMBRE_scraper.py
  2. Heredar de BaseScraper
  3. Definir SOURCE_CODE, INDEX_URLS
  4. Implementar fetch_index() y parse()
  5. Registrar en scraper_manager.py
"""
import abc
import hashlib
import time
import re
from datetime import datetime
from typing import Optional
import warnings

import requests
from bs4 import BeautifulSoup
from tenacity import (retry, stop_after_attempt,
                      wait_exponential, retry_if_exception_type)
import urllib3

import config
from utils.logger import get_logger

# ─── Proxy corporativo: silenciar advertencias de SSL ──────────────
if not config.VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BaseScraper(abc.ABC):
    """
    Clase base para scrapers de fuentes regulatorias colombianas.

    Subclases DEBEN definir:
        SOURCE_CODE : str         — código de la fuente (ej. "SFC")
        INDEX_URLS  : list[str]   — páginas de listado de normas

    Subclases DEBEN implementar:
        fetch_index() -> list[dict]          — lista de {url, title_hint}
        parse(html, url) -> dict | None      — extrae campos de una norma
    """

    SOURCE_CODE: str = ""
    INDEX_URLS: list[str] = []

    def __init__(self):
        self.log = get_logger(self.__class__.__name__.lower())
        self.session = self._build_session()

    # ── Sesión HTTP ──────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": config.USER_AGENT})
        s.verify = config.VERIFY_SSL
        return s

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        reraise=True,
    )
    def _get(self, url: str) -> Optional[requests.Response]:
        """GET con retry automático, timeout y delay de cortesía."""
        time.sleep(config.SCRAPER_DELAY_SECONDS)
        try:
            resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp
        except requests.HTTPError as e:
            self.log.warning(f"HTTP {e.response.status_code} — {url}")
            return None
        except requests.SSLError as e:
            self.log.error(
                f"SSL error en {url}. "
                "Si estás en red corporativa, verifica VERIFY_SSL=false en .env"
            )
            return None
        except Exception as e:
            self.log.error(f"Error inesperado en {url}: {e}")
            return None

    # ── Utilidades ───────────────────────────────────────────────────

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def _hash(self, texto: str) -> str:
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()

    def _norm_date(self, raw: str) -> str:
        """Normaliza fechas al formato DD/MM/YYYY."""
        raw = (raw or "").strip()
        if not raw:
            return ""
        meses_es = {
            "enero": "January", "febrero": "February", "marzo": "March",
            "abril": "April", "mayo": "May", "junio": "June",
            "julio": "July", "agosto": "August", "septiembre": "September",
            "octubre": "October", "noviembre": "November", "diciembre": "December",
        }
        norm = raw.lower()
        for es, en in meses_es.items():
            norm = norm.replace(es, en)
        for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d de %B de %Y",
                    "%d %B %Y", "%d-%m-%Y", "%Y/%m/%d",
                    "%d/%m/%y", "%B %d, %Y"]:
            try:
                return datetime.strptime(norm.title(), fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        # Intentar extraer solo el año como fallback
        match = re.search(r"\b(19|20)\d{2}\b", raw)
        return f"01/01/{match.group()}" if match else raw

    def _clean_text(self, text: str, max_chars: int = 100000) -> str:
        """Limpia espacios y trunca el texto."""
        return re.sub(r"\s+", " ", text).strip()[:max_chars]

    def _build_record(self, nombre: str, tipo_norma: str, autoridad: str,
                      fecha_expedicion: str, url: str, texto_completo: str) -> dict:
        """Construye un registro con el schema raw (ver SCHEMA_RAW en config.py)."""
        texto = self._clean_text(texto_completo)
        return {
            "id_externo":       self._hash(url),
            "fuente":           self.SOURCE_CODE,
            "nombre":           nombre.strip()[:config.MAX_NOMBRE],
            "tipo_norma":       tipo_norma.strip(),
            "autoridad":        autoridad.strip(),
            "fecha_expedicion": fecha_expedicion,
            "fecha_extraccion": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "url":              url.strip(),
            "texto_completo":   texto,
            "hash_contenido":   self._hash(texto),
        }

    # ── Métodos abstractos ───────────────────────────────────────────

    @abc.abstractmethod
    def fetch_index(self) -> list[dict]:
        """
        Devuelve lista de dicts {url: str, title_hint: str}
        con las URLs de normas individuales a procesar.
        """
        ...

    @abc.abstractmethod
    def parse(self, html: str, url: str) -> Optional[dict]:
        """
        Recibe el HTML de la página de una norma y devuelve
        un dict con schema raw, o None si no puede parsear.
        """
        ...

    # ── Orquestador ──────────────────────────────────────────────────

    def run(self, max_docs: int = 0) -> list[dict]:
        """
        Ejecuta el scraper completo.

        Args:
            max_docs: límite de normas (0 = sin límite). Usar 5-10 para testing.
        """
        self.log.info(
            f"[{self.SOURCE_CODE}] Iniciando"
            + (f" — modo test: max_docs={max_docs}" if max_docs else "")
        )

        items = self.fetch_index()
        self.log.info(f"[{self.SOURCE_CODE}] {len(items)} enlaces en el índice")

        if max_docs:
            items = items[:max_docs]

        resultados, errores = [], 0
        for i, item in enumerate(items, 1):
            url = item.get("url", "")
            if not url:
                continue
            try:
                resp = self._get(url)
                if resp is None:
                    errores += 1
                    continue
                record = self.parse(resp.text, url)
                if record:
                    resultados.append(record)
                    self.log.debug(
                        f"[{i}/{len(items)}] {record['nombre'][:70]}"
                    )
                else:
                    errores += 1
                    self.log.warning(f"[{i}/{len(items)}] Sin parseo: {url}")
            except Exception as e:
                errores += 1
                self.log.error(f"[{i}/{len(items)}] {url}: {e}")

        self.log.info(
            f"[{self.SOURCE_CODE}] Finalizado — "
            f"{len(resultados)} OK, {errores} errores"
        )
        return resultados
