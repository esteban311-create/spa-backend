"""
src/scraper/urf_scraper.py — Unidad de Regulación Financiera (URF)
ESTADO: ✅ FUNCIONANDO

Decisiones de diseño:
- Usa requests + BeautifulSoup — HTML estático, sin JavaScript.
- Extrae decretos de la página /transparencia/normativa/decretos/YYYY
- Filtra solo decretos (excluye documentos técnicos)
- URLs relativas se convierten a absolutas con base_url
"""

import re
import time
from typing import Optional

from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.scraper.base_scraper import BaseScraper
import config


class URFScraper(BaseScraper):

    SOURCE_CODE = "URF"
    BASE_URL    = "https://www.urf.gov.co"
    URL_DECRETOS_2026 = "https://www.urf.gov.co/transparencia/normativa/decretos/2026"

    # ── Parseo de fecha ────────────────────────────────────────────

    def _parsear_fecha_urf(self, href: str) -> str:
        """
        URF entrega fechas en la URL: "DECRETO+No.+0508+DEL+19+DE+MAYO+DE+2026.pdf"
        Extrae y convierte a DD/MM/YYYY.
        Patrón: DEL+DD+DE+MES+DE+YYYY
        """
        if not href:
            return ""

        # Decodificar URL para obtener nombre completo
        import urllib.parse
        href_decoded = urllib.parse.unquote_plus(href)
        

        # Buscar patrón "DEL DD DE MES DE YYYY"
        m = re.search(
            r"DEL\s+(\d{1,2})\s+DE\s+(\w+)\s+DE\s+(\d{4})",
            href_decoded.upper()
        )
        
        
        if m:
            dia, mes_txt, anio = m.group(1), m.group(2), m.group(3)
            meses = {
                "ENERO": "01", "FEBRERO": "02", "MARZO": "03",
                "ABRIL": "04", "MAYO": "05",   "JUNIO": "06",
                "JULIO": "07", "AGOSTO": "08", "SEPTIEMBRE": "09",
                "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
            }
            mes_num = meses.get(mes_txt)
            if mes_num:
                fecha_resultado = f"{int(dia):02d}/{mes_num}/{anio}"
                return fecha_resultado

        return ""

    # ── Extracción de número de decreto ────────────────────────────

    def _extraer_numero_decreto(self, nombre: str) -> str:
        """
        Extrae número del nombre: "Decreto 0508 de 2026" → "0508"
        """
        m = re.search(r"\d{3,4}", nombre)
        return m.group(0) if m else ""

    # ── Parseo de página ──────────────────────────────────────────

    def _parsear_pagina(self, html: str) -> list[dict]:
        """
        Extrae todos los decretos de la página.
        Filtra solo decretos (excluye "Documento Técnico").
        """
        soup = BeautifulSoup(html, "html.parser")
        normas = []

        # Encontrar el contenedor con PDFs
        container = None
        for div in soup.find_all("div", class_=lambda c: c and "lfr-layout-structure-item-container" in str(c)):
            links_pdf = div.find_all("a", href=lambda h: h and ".pdf" in str(h).lower())
            if len(links_pdf) >= 3:
                container = div
                break

        if not container:
            self.log.warning("URF: contenedor de decretos no encontrado")
            return []

        # Extraer todos los enlaces PDF
        enlaces = container.find_all("a", href=lambda h: h and ".pdf" in str(h).lower())

        for enlace in enlaces:
            nombre_raw = enlace.get_text(strip=True)

            # Filtrar: solo "Decreto XXXX", excluir "Documento Técnico"
            if "documento técnico" in nombre_raw.lower():
                continue
            if "decreto" not in nombre_raw.lower():
                continue

            href = enlace["href"]
            
            # Decodificar href para extraer la fecha que está en el nombre del PDF
            import urllib.parse
            href_decodificado = urllib.parse.unquote(href)
            
            numero = self._extraer_numero_decreto(nombre_raw)
            fecha = self._parsear_fecha_urf(href_decodificado)  # ← pasar href decodificado

            # URL absoluta
            url = href if href.startswith("http") else self.BASE_URL + href

            # ID externo
            id_externo = f"URF-{numero}" if numero else f"URF-{url.split('/')[-1]}"

            # Texto = nombre del decreto
            texto = self._clean_text(nombre_raw)

            norma = {
                "id_externo":       id_externo,
                "fuente":           "URF",
                "nombre":           nombre_raw,
                "tipo_norma":       "Decreto",
                "autoridad":        "Unidad de Regulación Financiera",
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
        """
        Scrape decretos URF de 2026.
        """
        self.log.info(
            f"[URF] Iniciando — {'max_docs=' + str(max_docs) if max_docs else 'producción'}"
        )

        r = self._get(self.URL_DECRETOS_2026)
        if not r:
            self.log.error("[URF] No se pudo acceder a la página")
            return []

        normas = self._parsear_pagina(r.text)
        self.log.info(f"[URF] {len(normas)} decretos extraídos")

        if max_docs and len(normas) > max_docs:
            normas = normas[:max_docs]

        self.log.info(f"[URF] Finalizado — {len(normas)} normas OK")
        return normas

    # ── Métodos abstractos requeridos ──────────────────────────────

    def fetch_index(self) -> list[str]:
        return [self.URL_DECRETOS_2026]

    def parse(self, url: str, html: str) -> Optional[dict]:
        return None
