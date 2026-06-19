"""
src/scraper/minhac_scraper.py — Ministerio de Hacienda y Crédito Público
ESTADO: ✅ FUNCIONANDO

Decisiones de diseño:
- Usa requests + BeautifulSoup — HTML estático, sin JavaScript.
- Extrae decretos de /decretos-2026 y resoluciones de /resoluciones-2026
- Fecha extraída del nombre: dos formatos posibles
  1. "DECRETO No. 0549 DEL 01 DE JUNIO DE 2026"
  2. "Resolucion_0102_enero_23_2026"
- Paginación: Liferay document_library con parámetro de vista
"""

import re
import urllib.parse
from typing import Optional
from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.scraper.base_scraper import BaseScraper
import config


class MinhacScraper(BaseScraper):

    SOURCE_CODE = "MINHAC"
    BASE_URL    = "https://www.minhacienda.gov.co"

    URLS_2026 = {
        "Decreto":    "https://www.minhacienda.gov.co/decretos-2026",
        "Resolución": "https://www.minhacienda.gov.co/resoluciones-2026",
    }

    MESES_ES = {
        "enero": "01", "febrero": "02", "marzo": "03",
        "abril": "04", "mayo": "05",   "junio": "06",
        "julio": "07", "agosto": "08", "septiembre": "09",
        "octubre": "10", "noviembre": "11", "diciembre": "12",
    }

    # ── Parseo de fecha ────────────────────────────────────────────

    def _parsear_fecha_minhac(self, nombre: str) -> str:
        """
        Soporta dos formatos:
        1. "DECRETO No. 0549 DEL 01 DE JUNIO DE 2026" → 01/06/2026
        2. "Resolucion_0102_enero_23_2026"            → 23/01/2026
        """
        if not nombre:
            return ""

        nombre_up = nombre.upper()

        # Formato 1: DEL DD DE MES DE YYYY
        m = re.search(
            r"DEL\s+(\d{1,2})\s+DE\s+(\w+)\s+DE\s+(\d{4})",
            nombre_up
        )
        if m:
            dia, mes_txt, anio = m.group(1), m.group(2), m.group(3)
            mes_num = self.MESES_ES.get(mes_txt.lower())
            if mes_num:
                return f"{int(dia):02d}/{mes_num}/{anio}"

        # Formato 2: _MES_DD_YYYY (ej: _enero_23_2026)
        m = re.search(
            r"_(\w+)_(\d{1,2})_(\d{4})",
            nombre.lower()
        )
        if m:
            mes_txt, dia, anio = m.group(1), m.group(2), m.group(3)
            mes_num = self.MESES_ES.get(mes_txt)
            if mes_num:
                return f"{int(dia):02d}/{mes_num}/{anio}"

        return ""

    # ── Detectar tipo ──────────────────────────────────────────────

    def _detectar_tipo(self, nombre: str, tipo_url: str) -> str:
        nombre_l = nombre.lower()
        if "circular" in nombre_l:
            return "Circular Externa"
        if "resoluci" in nombre_l:
            return "Resolución"
        if "decreto" in nombre_l:
            return "Decreto"
        return tipo_url

    # ── Parseo de tabla ────────────────────────────────────────────

    def _parsear_tabla(self, html: str, tipo_url: str) -> list[dict]:
        """
        Extrae normas de la tabla Liferay de MinHac.
        Estructura: <tr><td></td><td>NOMBRE</td><td>Descripción</td><td>Fecha</td><td></td></tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        normas = []

        tabla = soup.find("table")
        if not tabla:
            self.log.warning(f"MINHAC: tabla no encontrada para {tipo_url}")
            return []

        filas = tabla.find_all("tr")
        for fila in filas:
            celdas = fila.find_all("td")
            if len(celdas) < 2:
                continue

            # Buscar enlace con nombre de la norma
            enlace = fila.find("a", href=lambda h: h and "document_library" in str(h))
            if not enlace:
                continue

            nombre_raw = enlace.get_text(strip=True)
            if not nombre_raw or nombre_raw in ("Documentos", "Resoluciones y Circulares", "Decretos"):
                continue

            href = enlace["href"]
            url  = href if href.startswith("http") else self.BASE_URL + href

            # Descripción (celda 2 si existe)
            descripcion = celdas[2].get_text(strip=True) if len(celdas) > 2 else ""

            fecha = self._parsear_fecha_minhac(nombre_raw)
            tipo  = self._detectar_tipo(nombre_raw, tipo_url)

            # Número de norma
            m_num = re.search(r"(\d{3,4})", nombre_raw)
            numero = m_num.group(1) if m_num else ""
            id_externo = f"MINHAC-{tipo_url[:3].upper()}-{numero}" if numero else f"MINHAC-{self._hash(url)[:8]}"

            texto = self._clean_text(f"{nombre_raw} {descripcion}")

            norma = {
                "id_externo":       id_externo,
                "fuente":           "MINHAC",
                "nombre":           nombre_raw,
                "tipo_norma":       tipo,
                "autoridad":        "Ministerio de Hacienda y Crédito Público",
                "fecha_expedicion": fecha,
                "fecha_extraccion": __import__("datetime").datetime.now().strftime("%d/%m/%Y"),
                "url":              url,
                "texto_completo":   texto,
                "hash_contenido":   self._hash(texto),
            }
            normas.append(norma)

        return normas

    # ── run() ──────────────────────────────────────────────────────

    def run(self, max_docs: int = 0) -> list[dict]:
        self.log.info(
            f"[MINHAC] Iniciando — {'max_docs=' + str(max_docs) if max_docs else 'producción'}"
        )

        todas = []

        for tipo_url, url in self.URLS_2026.items():
            self.log.info(f"MINHAC: scraping {tipo_url} → {url}")
            r = self._get(url)
            if not r:
                self.log.error(f"MINHAC: no se pudo acceder a {url}")
                continue

            normas = self._parsear_tabla(r.text, tipo_url)
            todas.extend(normas)
            self.log.info(f"MINHAC: {len(normas)} {tipo_url}s extraídos")

        if max_docs and len(todas) > max_docs:
            todas = todas[:max_docs]

        self.log.info(f"[MINHAC] Finalizado — {len(todas)} normas OK")
        return todas

    # ── Métodos abstractos requeridos ──────────────────────────────

    def fetch_index(self) -> list[str]:
        return list(self.URLS_2026.values())

    def parse(self, url: str, html: str) -> Optional[dict]:
        return None
