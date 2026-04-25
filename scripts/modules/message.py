import asyncio
import base64
import io
import json as js
import re
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import discord

from .code import generate_code
from .logs import Logs

vt_semaphore = asyncio.Semaphore(4)


class Message:
    def __init__(self, msg: discord.Message):
        self.msg = msg
        self.scanned_url = None

    def _get_json_path(self, filename):
        base_dir = Path(__file__).parent.parent.parent
        return base_dir / "data" / filename

    def _load_json_list(self, filename):
        path = self._get_json_path(filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = js.load(f)
                if isinstance(data, list):
                    return data
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
            self.msg.content,
        )
        if not url_match:
            return False, None, None

        url = url_match.group(0)
        self.scanned_url = url
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if ":" in domain:
            domain = domain.split(":")[0]

        print(f"[DEBUG] URL: {url} | Dominio extraído: {domain}")

        gif_domains = self._load_json_list("whitelist.json")
        alert_domains = self._load_json_list("alert_domains.json")

        # 1. Si está en whitelist → omitir
        if self._domain_matches(domain, gif_domains):
            print(f"[INFO] Dominio {domain} en whitelist -> omitido")
            return False, domain, url

        # 2. Si está en alert_domains → alertar sin VT
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
        if not self.scanned_url:
            return False

        async with vt_semaphore:
            url_id = (
                base64.urlsafe_b64encode(self.scanned_url.encode()).decode().strip("=")
            )
            headers = {"x-apikey": api_key}
            vt_api_url = f"https://www.virustotal.com/api/v3/urls/{url_id}"

            try:
                async with session.get(vt_api_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        stats = (
                            data.get("data", {})
                            .get("attributes", {})
                            .get("last_analysis_stats", {})
                        )
                        malicious = stats.get("malicious", 0)
                        return malicious > 0
                    elif response.status == 404:
                        print(
                            f"[INFO VT] URL no encontrada, enviando a análisis: {self.scanned_url}"
                        )
                        submit_data = {"url": self.scanned_url}
                        async with session.post(
                            "https://www.virustotal.com/api/v3/urls",
                            headers=headers,
                            data=submit_data,
                        ) as post_resp:
                            if post_resp.status == 200:
                                await asyncio.sleep(5)
                                async with session.get(
                                    vt_api_url, headers=headers
                                ) as retry_resp:
                                    if retry_resp.status == 200:
                                        data = await retry_resp.json()
                                        stats = (
                                            data.get("data", {})
                                            .get("attributes", {})
                                            .get("last_analysis_stats", {})
                                        )
                                        malicious = stats.get("malicious", 0)
                                        return malicious > 0
                                    else:
                                        print(
                                            f"[ERROR VT] No se pudo obtener el análisis después del envío: {retry_resp.status}"
                                        )
                                        return False
                            else:
                                print(
                                    f"[ERROR VT] Fallo al enviar URL: {post_resp.status}"
                                )
                                return False
                    elif response.status == 429:
                        print("[ERROR VT] Límite alcanzado, esperando 60s...")
                        await asyncio.sleep(60)
                        return None
                    else:
                        print(f"[ERROR VT] Error inesperado: {response.status}")
                        return False
            except aiohttp.ClientError as e:
                print(f"[ERROR VT] Error de red: {e}")
                return False

    async def transcribe_audio(self, GROQ_CLIENT, member: discord.Member = None):
        if not self.msg.attachments:
            return
        audio_attachment = self.msg.attachments[0]
        print(
            f"[DEBUG] Transcribing audio: {audio_attachment.filename} (type: {audio_attachment.content_type})"
        )

        # Aceptamos cualquier tipo que empiece por "audio/"
        if (
            not audio_attachment.content_type
            or not audio_attachment.content_type.startswith("audio/")
        ):
            print(
                f"[DEBUG] Formato de audio no soportado: {audio_attachment.content_type}"
            )
            return (
                "",
                "❌ Formato no soportado",
                f"No se pudo transcribir: tipo {audio_attachment.content_type}",
            )

        try:
            audio_bytes = await audio_attachment.read()
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = audio_attachment.filename

            transcription = await GROQ_CLIENT.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                response_format="text",
            )

            reference = (
                f"Mandado a: {member.mention}"
                if self.msg.author.id != member.id
                else ""
            )
            return (
                "",
                "📝 Transcripción de audio",
                f"{reference}\n**Contenido:**\n```{transcription}```",
            )
        except Exception as e:
            print(f"[ERROR] Transcripción fallida: {e}")
            return (
                "",
                "❌ Error de transcripción",
                f"No se pudo transcribir: {str(e)}",
            )

    async def Misconduct(self, groq_client):
        if not self.msg.content or len(self.msg.content.strip()) == 0:
            return False

        async def _call_groq():
            prompt_instrucciones = """
                Analiza el siguiente texto en español (o mezcla inglés/español).
                Responde **ÚNICAMENTE** 'True' o 'False' según las siguientes reglas estrictas:

                **Responde 'True' SOLO SI se cumple AL MENOS UNA de estas condiciones:**
                1. Contiene **insultos graves o blasfemias** dirigidos **explícitamente** a una persona o grupo (Ej: "Eres un hijo de puta", "Idiota de mierda", "Vete a la verga, [nombre]").
                2. Contiene **propuestas o descripciones sexuales explícitas** (Ej: "Quiero cogerte", "Manda nudes", descripciones gráficas de actos).
                3. Intenta obtener o revelar **información privada (Doxxing)** como dirección, teléfono, o datos personales reales (Ej: "¿Cuál es tu dirección?", "Vivo en la calle X").
                4. Contiene **amenazas graves** de cualquier tipo (físicas, de muerte, daño psicológico, represalias, etc.) dirigidas explícitamente contra una persona o grupo (Ej: "Te voy a matar", "Voy a hacer que te despidan", "Deberías tener miedo", "Ojalá te enfermes gravemente").

                **Responde 'False' en estos casos (No son considerados 'Misconduct' grave para este filtro):**
                - Palabras soeces usadas como **muletillas o exclamaciones** sin un objetivo personal (Ej: "¡Joder, qué mal día!", "Mierda, perdí el tren").
                - Insultos leves genéricos no dirigidos a nadie (Ej: "Esto es una estupidez").
                - Texto que menciona las malas palabras pero no las usa para atacar (Ej: "Me dijo una mala palabra").
                - Expresiones hiperbólicas o coloquiales que no constituyen una amenaza real (Ej: "¡Me muero de risa!", "Como me entere, lo mato… de risa").

                **IMPORTANTE SOBRE EL LENGUAJE:**
                Debes detectar las palabras malsonantes o amenazas incluso si están:
                - Escritas con caracteres especiales o números (Ej: "p*ta", "h1j0", "c0ñ0", "m4t4r").
                - Separadas por puntos o espacios (Ej: "h i j o d e p u t a", "t e   v o y   a   m a t a r").

                Texto a analizar:
                "{texto_usuario}"

                Respuesta (solo 'True' o 'False'):
                """

            try:
                chat_completion = await asyncio.wait_for(
                    groq_client.chat.completions.create(
                        messages=[
                            {
                                "role": "user",
                                "content": prompt_instrucciones.format(
                                    texto_usuario=self.msg.content.strip()
                                ),
                            }
                        ],
                        model="llama-3.3-70b-versatile",
                        temperature=0.0,
                    ),
                    timeout=10.0,
                )
                response = chat_completion.choices[0].message.content.strip().lower()
                return response.startswith("true")
            except asyncio.TimeoutError:
                print(f"[Groq] Timeout al analizar mensaje: {self.msg.content[:50]}...")
                return False
            except Exception as e:
                print(f"[Groq] Error en la API: {e}")
                return False

        return await _call_groq()

    async def _ref_message(self, role_id, GROQ_CLIENT):
        print(
            f"[REF] _ref_message llamado para msg {self.msg.id} con referencia a {self.msg.reference.message_id if self.msg.reference else 'None'}"
        )
        try:
            ref_message = await self.msg.channel.fetch_message(
                self.msg.reference.message_id
            )
        except discord.NotFound:
            print("[REF] Mensaje referenciado no encontrado")
            return

        if ref_message.author == self.msg.author and not discord.utils.get(
            self.msg.author.roles, id=role_id
        ):
            print("[DEBUG _ref] El autor responde a su propio mensaje → ignorar")
            return

        # ¿Tiene el usuario original el rol protegido?
        has_role = any(
            r.id == role_id for r in ref_message.author.roles
        ) or discord.utils.get(self.msg.author.roles, id=role_id)
        print(
            f"[DEBUG _ref] Roles del autor original: {[r.name for r in ref_message.author.roles]} | Buscando rol {role_id} → {has_role}"
        )
        if not has_role:
            print("[DEBUG _ref] El autor NO tiene el rol protegido → ignorar")
            return

        if self.msg.attachments:
            att = self.msg.attachments[0]
            print(
                f"[DEBUG _ref] Adjunto en la respuesta: {att.filename} (type: {att.content_type})"
            )
            if att.content_type and att.content_type.startswith("audio/"):
                print(
                    "[DEBUG _ref] Es un audio, procediendo a transcribir la respuesta..."
                )
                transcription = await self.transcribe_audio(
                    GROQ_CLIENT,
                    ref_message.author,  # "Mandado a: <usuario protegido>"
                )
                print(f"[DEBUG _ref] Resultado transcripción: {transcription}")
                if transcription:
                    return transcription
                else:
                    print("[DEBUG _ref] La transcripción devolvió None")
                    # Podrías enviar una alerta de error, pero lo dejamos pasar
                    return
            else:
                print("[DEBUG _ref] El adjunto NO es audio")

        # Si no había audio en la respuesta, seguir con misconduct sobre el texto
        print("[DEBUG _ref] Evaluando misconduct en el texto de la respuesta...")
        misconduct = await self.Misconduct(GROQ_CLIENT)
        if misconduct:
            code = generate_code()
            if not discord.utils.get(self.msg.author.roles, id=role_id):
                logs = Logs()
                logs.addAlert(
                    self.msg.author.id,
                    code,
                    f"Msg INA. [to {ref_message.author.mention}]",
                    self.msg.jump_url,
                )
            return (
                code,
                "❗ Mensaje inapropiado",
                f"Dicho a: {ref_message.author.mention}\n**Contenido:**\n```{self.msg.content}```",
            )
        else:
            print("[DEBUG _ref] No se detectó misconduct")

    async def _mention_user(self, ids, role_id, GROQ_CLIENT):
        # Filtramos IDs no válidos (miembros que no están en el servidor)
        members = [
            m
            for m in (
                discord.utils.get(self.msg.guild.members, id=int(mid)) for mid in ids
            )
            if m is not None
        ]

        for member in members:
            if any(map(lambda r: r.id == role_id, member.roles)):
                misconduct = await self.Misconduct(GROQ_CLIENT)
                if misconduct:
                    code = generate_code()
                    # CORRECCIÓN: Verificar si el autor del mensaje (el que menciona) tiene el rol protegido
                    if not discord.utils.get(self.msg.author.roles, id=role_id):
                        logs = Logs()
                        logs.addAlert(
                            self.msg.author.id,
                            code,
                            "Msg INA. [Protect M.]",
                            self.msg.jump_url,
                        )

                    return (
                        code,
                        "❗ Mensaje inapropiado",
                        f"Protegidos: {', '.join([m.mention for m in members if discord.utils.get(m.roles, id=role_id)])}\n**Contenido:**\n```{self.msg.content}```",
                    )
