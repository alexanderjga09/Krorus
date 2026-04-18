import asyncio
import base64
import json as js
import re
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

vt_semaphore = asyncio.Semaphore(4)


class Message:
    def __init__(self, content):
        self.content = content
        self.scanned_url = None

    def _get_json_path(self, filename):
        base_dir = Path(__file__).parent.parent
        return base_dir / filename

    def _load_json_list(self, filename):
        path = self._get_json_path(filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = js.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "domains" in data:
                    return data["domains"]
                else:
                    print(f"Formato JSON inesperado en {path}: {type(data)}")
                    return []
        except FileNotFoundError:
            print(f"Archivo no encontrado: {path}")
            return []
        except js.JSONDecodeError as e:
            print(f"Error JSON en {path}: {e}")
            return []

    def _normalize_domain(self, domain):
        domain = domain.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    def _domain_matches(self, domain, pattern_list):
        domain = self._normalize_domain(domain)
        for pattern in pattern_list:
            pattern = self._normalize_domain(pattern)
            if domain == pattern or domain.endswith(f".{pattern}"):
                return True
        return False

    async def CheckAndAlert(self, vt_api_key, session):
        """Versión asíncrona que también escanea con VirusTotal si es necesario"""
        url_match = re.search(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            self.content,
        )
        if not url_match:
            return False, None, None

        url = url_match.group(0)
        self.scanned_url = url  # guardar para el método _scan_url_vt
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if ":" in domain:
            domain = domain.split(":")[0]

        print(f"[DEBUG] URL: {url} | Dominio extraído: {domain}")

        gif_domains = self._load_json_list("whitelist.json")
        alert_domains = self._load_json_list("alert_domains.json")

        # 1. Si es GIF -> omitir
        if self._domain_matches(domain, gif_domains):
            print(f"[INFO] Dominio {domain} en whitelist (GIFs) -> omitido")
            return False, domain, url

        # 2. Si está en alert_domains -> alertar sin VT
        if self._domain_matches(domain, alert_domains):
            print(f"[ALERTA] Dominio {domain} coincide con lista de alerta")
            return True, domain, url

        print(
            f"[INFO] Dominio {domain} no está en listas locales, escaneando con VT..."
        )
        is_malicious = await self._scan_url_vt(session, vt_api_key)

        if is_malicious is None:
            print("[INFO VT] Escaneo fallido o límite alcanzado, se asume seguro")
            return False, domain, url
        elif is_malicious:
            print("[ALERTA VT] URL maliciosa detectada")
            return True, domain, url
        else:
            print("[INFO] URL segura según VT")
            return False, domain, url

    async def _scan_url_vt(self, session, api_key):
        """Escanea la URL almacenada en self.scanned_url con VirusTotal, respetando límite de 4/min."""
        if not self.scanned_url:
            return False

        async with vt_semaphore:
            url_id = (
                base64.urlsafe_b64encode(self.scanned_url.encode()).decode().strip("=")
            )
            vt_api_url = f"https://www.virustotal.com/api/v3/urls/{url_id}"
            headers = {"x-apikey": api_key}

            try:
                async with session.get(vt_api_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        stats = (
                            data.get("data", {})
                            .get("attributes", {})
                            .get("last_analysis_stats", {})
                        )
                        malicious_count = stats.get("malicious", 0)
                        if malicious_count > 0:
                            print(
                                f"[ALERTA VT] URL MALICIOSA: {self.scanned_url} (Detectada por {malicious_count} motores)"
                            )
                            return True
                        else:
                            print(f"[INFO VT] URL segura: {self.scanned_url}")
                            return False
                    elif response.status == 429:
                        print(
                            "[ERROR VT] Límite de API alcanzado (4/min o 500/día). Esperando 60s..."
                        )
                        await asyncio.sleep(60)
                        return None
                    else:
                        print(f"[ERROR VT] Error en la API: {response.status}")
                        return False
            except aiohttp.ClientError as e:
                print(f"[ERROR VT] Error de red: {e}")
                return False

    async def Misconduct(self, groq_client):
        if not self.content or len(self.content.strip()) == 0:
            return False

        def _call_groq():
            try:
                chat_completion = groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Does this text contain bad words and their abbreviations, is it sexual in nature, "
                                "or is it about doxxing (obtaining information about someone's home address)? "
                                "If so, respond only 'True'. If not, respond only 'False'.\n\n"
                                f"Text: {self.content}"
                            ),
                        }
                    ],
                    model="llama-3.3-70b-versatile",
                    timeout=5.0,  # tiempo máximo de espera
                )
                response = chat_completion.choices[0].message.content.strip().lower()
                return response == "true" or response.startswith("true")
            except Exception as e:
                print(f"Error en Groq API: {e}")
                return False

            # Ejecutar en un hilo separado para no bloquear asyncio

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _call_groq)
        return result
