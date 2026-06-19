"""
src/scraper/banrep_scraper.py — Banco de la República
ESTADO: ✅ FUNCIONANDO

Decisiones de diseño:
- Usa Selenium + Edge VISIBLE (sin headless) porque BanRep tiene
  Radware Bot Manager que bloquea headless y requests paginados.
- Recorre páginas ?page=N mientras todas las fechas sean 2026.
- Para automáticamente cuando aparece un año anterior a 2026.
- 6 normas por página, ~4-5 páginas para cubrir todo 2026.
"""

import re
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.scraper.base_scraper import BaseScraper
import config


class BanRepScraper(BaseScraper):

    SOURCE_CODE = "BANREP"
    BASE_URL    = "https://www.banrep.gov.co"
    URL_NORMAS  = "https://www.banrep.gov.co/es/normatividad"
    AÑO_FILTRO  = "2026"

    MESES_ES = {
        "enero": "01", "febrero": "02", "marzo": "03",
        "abril": "04", "mayo": "05",   "junio": "06",
        "julio": "07", "agosto": "08", "septiembre": "09",
        "octubre": "10", "noviembre": "11", "diciembre": "12",
    }

    TIPO_PATTERNS = [
        (re.compile(r"circular externa",              re.I), "Circular Externa"),
        (re.compile(r"carta circular",                re.I), "Carta Circular"),
        (re.compile(r"bolet[ií]n.*junta|junta.*bolet", re.I), "Boletín Junta Directiva"),
        (re.compile(r"resoluci[oó]n",                 re.I), "Resolución"),
        (re.compile(r"decreto",                       re.I), "Decreto"),
    ]

    # ── Selenium ───────────────────────────────────────────────────

    def _build_driver(self) -> webdriver.Edge:
        """Edge VISIBLE — Radware bloquea headless."""
        service = Service(config.EDGE_DRIVER_PATH)
        options = webdriver.EdgeOptions()
        # ⚠ NO agregar --headless — Radware lo detecta y bloquea
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
        )
        driver = webdriver.Edge(service=service, options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        return driver

    # ── Parseo de fecha BanRep ─────────────────────────────────────

    def _parsear_fecha_banrep(self, fecha_raw: str) -> str:
        """
        BanRep entrega fechas como "Jueves, 11 de junio de 2026".
        Convierte a DD/MM/YYYY.
        """
        if not fecha_raw:
            return ""
        m = re.search(
            r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
            fecha_raw.lower()
        )
        if m:
            dia, mes_txt, anio = m.group(1), m.group(2), m.group(3)
            mes_num = self.MESES_ES.get(mes_txt)
            if mes_num:
                return f"{int(dia):02d}/{mes_num}/{anio}"
        return self._norm_date(fecha_raw)

    # ── Detectar tipo norma ────────────────────────────────────────

    def _detectar_tipo(self, tipo_raw: str) -> str:
        for patron, tipo in self.TIPO_PATTERNS:
            if patron.search(tipo_raw):
                return tipo
        return tipo_raw.strip() or "Otro"

    # ── Parseo de tabla ────────────────────────────────────────────

    def _parsear_tabla(self, html: str) -> tuple[list[dict], bool]:
        """
        Extrae normas de la tabla de la página.
        Retorna (lista_normas, hay_normas_anteriores_a_2026).
        hay_normas_anteriores=True significa que debemos parar la paginación.
        """
        soup = BeautifulSoup(html, "html.parser")
        tablas = soup.find_all("table")

        # Buscar la tabla que tiene columnas Tipo/Número/Asunto
        tabla = None
        for t in tablas:
            headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
            if any("tipo" in h for h in headers) and any("asunto" in h for h in headers):
                tabla = t
                break

        if tabla is None:
            self.log.warning("BANREP: tabla de normas no encontrada en HTML")
            return [], False
        filas = tabla.find_all("tr")[1:]  # saltar header

        normas = []
        hay_anteriores = False

        for fila in filas:
            celdas = fila.find_all("td")
            if len(celdas) < 4:
                continue

            tipo_raw  = celdas[0].get_text(strip=True)
            numero    = celdas[1].get_text(strip=True)
            asunto    = celdas[2].get_text(strip=True)
            fecha_raw = celdas[3].get_text(strip=True)

                    # Verificar año
            m_año = re.search(r"(20\d{2})", fecha_raw)
            año   = m_año.group(1) if m_año else ""

            if año and int(año) < 2026:
                hay_anteriores = True
                continue

            if año and int(año) > 2026:
                continue

            # Enlace de la norma
            enlace = fila.find("a", href=True)
            href   = enlace["href"] if enlace else ""
            url    = href if href.startswith("http") else self.BASE_URL + href

            # ID externo: número de la norma o slug de la URL
            id_externo = f"BANREP-{numero}" if numero else f"BANREP-{url.split('/')[-1]}"

            # Texto completo = asunto (descripción de la tabla)
            texto = self._clean_text(asunto)

            norma = {
                "id_externo":       id_externo,
                "fuente":           "BANREP",
                "nombre":           f"{tipo_raw} {numero} — {asunto}"[:200],
                "tipo_norma":       self._detectar_tipo(tipo_raw),
                "autoridad":        "Banco de la República",
                "fecha_expedicion": self._parsear_fecha_banrep(fecha_raw),
                "fecha_extraccion": __import__('datetime').datetime.now().strftime("%d/%m/%Y"),
                "url":              url,
                "texto_completo":   texto,
                "hash_contenido":   self._hash(texto),
            }
            normas.append(norma)

            fecha_raw = celdas[3].get_text(strip=True)
            m_año = re.search(r"(20\d{2})", fecha_raw)
            año   = m_año.group(1) if m_año else ""

        return normas, hay_anteriores

    # ── run() sobreescrito ─────────────────────────────────────────

    def run(self, max_docs: int = 0) -> list[dict]:
        """
        Recorre páginas ?page=N con Selenium visible.
        Para cuando aparece año anterior a 2026 o se alcanza max_docs.
        """
        self.log.info(
            f"[BANREP] Iniciando — {'max_docs=' + str(max_docs) if max_docs else 'producción'}"
        )
        self.log.info("BANREP: abriendo Edge visible (Radware requiere navegador real)")

        driver = self._build_driver()
        todas  = []

        try:
            page = 0
            while True:
                url = f"{self.URL_NORMAS}?page={page}"
                self.log.info(f"BANREP: página {page} → {url}")

                driver.get(url)
                time.sleep(4)  # espera para que Radware valide

                normas_pagina, hay_anteriores = self._parsear_tabla(driver.page_source)

                if not normas_pagina and not hay_anteriores:
                    self.log.warning(f"BANREP: página {page} sin normas — posible bloqueo")
                    break


                todas.extend(normas_pagina)
                self.log.info(f"BANREP: {len(todas)} normas acumuladas")

                # Condiciones de parada
                if hay_anteriores:
                    self.log.info("BANREP: detectado año anterior a 2026 — fin de paginación")
                    break

                if max_docs and len(todas) >= max_docs:
                    todas = todas[:max_docs]
                    self.log.info(f"BANREP: límite max_docs={max_docs} alcanzado")
                    break

                page += 1
                time.sleep(2)  # cortesía entre páginas

        except WebDriverException as e:
            self.log.error(f"BANREP: WebDriverException — {e}")
        finally:
            driver.quit()

        self.log.info(f"[BANREP] Finalizado — {len(todas)} normas OK")
        return todas

    # ── Métodos abstractos requeridos ──────────────────────────────

    def fetch_index(self) -> list[str]:
        return [self.URL_NORMAS]

    def parse(self, url: str, html: str) -> Optional[dict]:
        return None
