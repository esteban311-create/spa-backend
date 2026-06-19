"""
src/scraper/sfc_scraper.py — Superintendencia Financiera de Colombia.
Usa Selenium para leer la tabla (cargada con JS) y descarga cada norma
directamente desde loader.php como PDF, extrayendo el texto con pdfminer.
"""
import re
import time
import io
from typing import Optional

from selenium import webdriver
from selenium.webdriver.edge.service import Service
import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from pdfminer.high_level import extract_text as pdf_extract
    PDF_OK = True
except ImportError:
    PDF_OK = False

from base_scraper import BaseScraper
import config


class SFCScraper(BaseScraper):

    SOURCE_CODE = "SFC"
    BASE_URL    = "https://www.superfinanciera.gov.co"

    # ── Páginas de listado 2026 ──────────────────────────────────
    INDEX_URLS = [
        "https://www.superfinanciera.gov.co/publicaciones/10115974/circulares-externas-2026/",
        "https://www.superfinanciera.gov.co/publicaciones/10115976/resoluciones-2026/",
        "https://www.superfinanciera.gov.co/publicaciones/10115975/cartas-circulares-2026/",
    ]

    # Tipo por página de listado
    TIPO_MAP = {
        "10115974": "Circulares",
        "10115976": "Resolución",
        "10115975": "Circulares",
    }

    
    def _build_driver(self):
        service = Service(config.EDGE_DRIVER_PATH)
        options = webdriver.EdgeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--log-level=3")
        return webdriver.Edge(service=service, options=options)

    def _extraer_tipo(self, idx_url: str) -> str:
        for key, tipo in self.TIPO_MAP.items():
            if key in idx_url:
                return tipo
        return "Circulares"

    def fetch_index(self) -> list[dict]:
        """
        Usa Selenium para leer la tabla de cada página de listado.
        Extrae: número, fecha, descripción, URL del PDF (idFile).
        """
        items = []

        for idx_url in self.INDEX_URLS:
            tipo = self._extraer_tipo(idx_url)
            self.log.info(f"SFC: leyendo tabla → {idx_url}")

            driver = self._build_driver()
            try:
                driver.get(idx_url)
                time.sleep(8)
                soup = self._soup(driver.page_source)
            finally:
                driver.quit()

            tabla = soup.find('table')
            if not tabla:
                self.log.warning(f"SFC: sin tabla en {idx_url}")
                continue

            filas = tabla.find_all('tr')[1:]  # saltar encabezado
            for fila in filas:
                celdas = fila.find_all('td')
                if len(celdas) < 3:
                    continue

                # Número de la norma (ej: "006")
                numero = celdas[0].get_text(strip=True)

                # URL del PDF — primer link de la fila
                pdf_link = fila.find('a', href=True)
                if not pdf_link:
                    continue
                href = pdf_link['href']
                if not href.startswith('http'):
                    href = self.BASE_URL + href

                # Fecha (ej: "Mayo 11")
                fecha_partes = celdas[1].get_text(strip=True).split() if len(celdas) > 1 else []
                if len(fecha_partes) == 2:
                    fecha_raw = f"{fecha_partes[1]}/{fecha_partes[0]}/2026"
                else:
                    fecha_raw = celdas[1].get_text(strip=True)


                # Descripción
                desc = celdas[2].get_text(strip=True) if len(celdas) > 2 else ""

                # Nombre completo
                año = "2026"
                nombre = f"{tipo} {numero} de {año} — {desc[:120]}"

                items.append({
                    "url":        href,
                    "title_hint": nombre,
                    "numero":     numero,
                    "fecha_raw":  fecha_raw,
                    "descripcion":desc,
                    "tipo_norma": tipo,
                    "nombre":     nombre,
                })

            self.log.info(f"SFC: {len(items)} normas acumuladas")

        return items

    def _extraer_texto_pdf(self, url: str) -> str:
        """Descarga el PDF y extrae el texto con pdfminer."""
        if not PDF_OK:
            return "pdfminer no instalado — solo metadatos disponibles"
        try:
            resp = self.session.get(url, timeout=30, verify=config.VERIFY_SSL)
            texto = pdf_extract(io.BytesIO(resp.content))
            return self._clean_text(texto or "")
        except Exception as e:
            self.log.warning(f"No se pudo extraer PDF {url}: {e}")
            return ""

    def parse(self, html: str, url: str) -> Optional[dict]:
        """
        Para la SFC no usamos parse() con HTML — los datos vienen
        directamente de fetch_index() (tabla) y el texto del PDF.
        Este método queda como fallback por compatibilidad con BaseScraper.
        """
        return None

    def run(self, max_docs: int = 0) -> list[dict]:
        """
        Override de run() porque la SFC no sigue el patrón
        fetch_index → GET html → parse. Aquí es:
        fetch_index (tabla via Selenium) → descargar PDF → extraer texto
        """
        self.log.info(
            f"[SFC] Iniciando"
            + (f" — modo test: max_docs={max_docs}" if max_docs else "")
        )

        items = self.fetch_index()
        self.log.info(f"[SFC] {len(items)} normas en la tabla")

        if max_docs:
            items = items[:max_docs]

        resultados, errores = [], 0

        for i, item in enumerate(items, 1):
            url = item["url"]
            try:
                # Extraer texto del PDF
                texto = self._extraer_texto_pdf(url)
                
                record = self._build_record(
                    nombre=item["nombre"],
                    tipo_norma=item["tipo_norma"],
                    autoridad="Superintendencia Financiera de Colombia",
                    fecha_expedicion=self._parsear_fecha_sfc(item["fecha_raw"]),
                    url=url,
                    texto_completo=item["descripcion"]
                )
                resultados.append(record)
                self.log.debug(f"[{i}/{len(items)}] {item['nombre'][:70]}")

            except Exception as e:
                errores += 1
                self.log.error(f"[{i}/{len(items)}] {url}: {e}")

        self.log.info(
            f"[SFC] Finalizado — {len(resultados)} OK, {errores} errores"
        )
        return resultados
    
    def _parsear_fecha_sfc(self, fecha_raw: str) -> str:
        """Convierte '11/Mayo/2026' → '11/05/2026'"""
        meses = {
            "enero":"01","febrero":"02","marzo":"03","abril":"04",
            "mayo":"05","junio":"06","julio":"07","agosto":"08",
            "septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"
        }
        try:
            partes = fecha_raw.lower().strip().split("/")
            # partes = ['11', 'mayo', '2026']
            if len(partes) == 3:
                dia  = partes[0].zfill(2)
                mes  = meses.get(partes[1], "01")
                anio = partes[2]
                return f"{dia}/{mes}/{anio}"
        except Exception:
            pass
        return "01/01/2026"
            