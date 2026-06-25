import asyncio
import datetime
import hashlib
import json
import logging
import logging.handlers
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from groq import AsyncGroq

from .cogs.append_alertdomain import AppendAlertDomain
from .cogs.append_ignoreword import AppendIgnoreWord
from .cogs.append_whitelist import AppendWhitelistDomain
from .cogs.check_user import CheckUser
from .cogs.exif_check import ExifCheck
from .cogs.health import HealthCheck
from .cogs.list_users import ListUsers
from .cogs.set_data import SetData
from .cogs.whisper import Whisper
from .modules.chainlog import get_chain_log
from .modules.code import generate_code
from .modules.database import read_row, try_read_row
from .modules.message import Message

load_dotenv()

# Logging setup
_log_dir = Path(__file__).parent.parent / "data"
_log_dir.mkdir(parents=True, exist_ok=True)


class _CleanErrorFilter(logging.Filter):
    _NOISY = (
        "discord.client",
        "discord.gateway",
        "discord.http",
        "aiohttp.client",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name not in self._NOISY:
            return True
        msg = record.getMessage()
        if "Attempting a reconnect" in msg:
            record.exc_info = None
            record.exc_text = None
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            _log_dir / "krorus.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
    ],
)
for name in _CleanErrorFilter._NOISY:
    logging.getLogger(name).addFilter(_CleanErrorFilter())
logger = logging.getLogger("krorus")

def _build_groq_client() -> AsyncGroq | None:
    """Crea el cliente de Groq de forma tolerante.

    Si la API key no esta configurada (o el constructor falla) devuelve None en
    lugar de abortar el arranque del bot. Las funciones que dependen de Groq
    deben tratar el cliente None como "IA no disponible".
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning(
            "⚠️ GROQ_API_KEY no configurada — el analisis de IA y la "
            "transcripcion de audio quedaran deshabilitados."
        )
        return None
    try:
        return AsyncGroq(api_key=api_key)
    except Exception as e:
        logger.error(f"No se pudo inicializar el cliente Groq: {e}")
        return None


GROQ_CLIENT = _build_groq_client()

# Leer configuracion de BD y validar
BD = try_read_row()
STAFF_CHANNEL_ID = BD[0]
PROTECTED_ROLE_ID = BD[1]

# Aviso si los datos no estan configurados
if not STAFF_CHANNEL_ID or not PROTECTED_ROLE_ID:
    logger.warning(
        "⚠️ ADVERTENCIA: STAFF_CHANNEL_ID o PROTECTED_ROLE_ID no estan configurados en la base de datos."
    )

PATH_IGNORE_WORDS = Path(__file__).parent.parent / "data" / "ignorewords.json"

# Cargar configuracion del bot desde data/bot_config.json (opcional)
BOT_CONFIG_PATH = Path(__file__).parent.parent / "data" / "bot_config.json"
DEFAULTS = {
    "log_multimedia": True,
    "transcribe_audio": True,
    "log_message_edits": True,
    "enable_whisper": True,
    "monitor_voice_channels": True,
    "detailed_logging": False,
    "groq_timeout": 10.0,
    "groq_audio_timeout": 30.0,
    "check_exif_metadata": True,
}

try:
    if BOT_CONFIG_PATH.exists():
        with BOT_CONFIG_PATH.open("r", encoding="utf-8") as _f:
            _raw = json.load(_f)
            BOT_CONFIG = {**DEFAULTS, **_raw}
    else:
        BOT_CONFIG = DEFAULTS.copy()
except Exception as e:
    logger.warning(f"No se pudo cargar bot_config.json: {e}")
    BOT_CONFIG = DEFAULTS.copy()

# Ajustes de diagnostico segun configuracion
if BOT_CONFIG.get("detailed_logging", False):
    logger.setLevel(logging.DEBUG)


class Krorus(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(intents=intents, sync_commands=True)
        self.allowed_guild_id = int(os.getenv("ALLOWED_GUILD_ID", "0"))
        self.http_session: aiohttp.ClientSession | None = None
        self.bot_config: dict = {}
        self._rate_limit_until: float = 0
        self._rate_limit_lock = threading.Lock()
        # Buffer de mensajes (sala de espera) para análisis por lotes con Groq
        self._msg_buffer: dict[
            int, dict
        ] = {}  # channel_id -> {user_id, messages, task}
        self._buffer_lock = asyncio.Lock()
        self._data_lock = asyncio.Lock()
        self._buffer_flush_delay: int = 60
        self.staff_channel_id: int = STAFF_CHANNEL_ID
        self.protected_role_id: int = PROTECTED_ROLE_ID
        # Cooldown por canal de voz para no spamear la misma alerta de
        # supervision en cada join/leave. channel_id -> timestamp ultima alerta
        self._voice_alert_cooldown: dict[int, float] = {}
        # IDs de mensajes que ya dispararon alerta (+ timestamp). Se filtran
        # del lookback para evitar doble/triple penalización por el mismo texto.
        self._flagged_msg_ids: dict[int, float] = {}
        # IDs de mensajes que pasaron por el buffer (activo o ya procesado).
        self._buffered_msg_ids: dict[int, float] = {}

    def get_config(self, key: str, default=None):
        """Lee un valor de configuracion. Siempre refleja el estado actual."""
        return self.bot_config.get(key, default)

    @staticmethod
    def _file_kwargs(file) -> dict:
        if isinstance(file, list):
            clean = [f for f in file if f is not None]
            return {"files": clean} if clean else {}
        elif file is not None:
            return {"file": file}
        return {}

    def check_rate_limit(self, action: str = "general") -> bool:
        """Verifica si esta rate-limited. Devuelve True si puede proceder."""
        with self._rate_limit_lock:
            if time.time() < self._rate_limit_until:
                logger.warning(
                    f"[RATE LIMIT] {action}: bloqueado hasta {self._rate_limit_until}"
                )
                return False
        return True

    def set_rate_limit(self, seconds: int, reason: str = ""):
        """Activa rate limit por X segundos."""
        with self._rate_limit_lock:
            self._rate_limit_until = time.time() + seconds
        logger.warning(f"[RATE LIMIT] Activado por {seconds}s: {reason}")

    def is_rate_limited(self) -> bool:
        """True si el bot esta actualmente en pausa por rate limit."""
        with self._rate_limit_lock:
            return time.time() < self._rate_limit_until

    def _maybe_rate_limit(self, exc: Exception) -> None:
        """Si la excepcion es un 429 de Discord, activa backpressure global."""
        if isinstance(exc, discord.HTTPException) and getattr(exc, "status", None) == 429:
            retry = getattr(exc, "retry_after", None) or 30
            self.set_rate_limit(int(retry), "Discord HTTP 429 al enviar alerta")

    # ── Sistema de buffer/sala de espera para Groq ────────────────────────

    def _is_flagged(self, msg_id: int) -> bool:
        """True si el mensaje ya fue penalizado y su flag no ha expirado."""
        expiry = self._flagged_msg_ids.get(msg_id)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._flagged_msg_ids[msg_id]
            return False
        return True

    def _was_in_buffer(self, msg_id: int) -> bool:
        """True si el mensaje estuvo (o está) en un buffer reciente."""
        expiry = self._buffered_msg_ids.get(msg_id)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._buffered_msg_ids[msg_id]
            return False
        return True

    async def _buffer_add(
        self,
        message: discord.Message,
        lookback: bool = False,
        vt_api_key: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ):
        """Buffer de mensajes: acumula texto de usuarios protegidos hasta
        que otro usuario hable en el canal o pasen 60s sin actividad.
        Si lookback=True, busca mensajes recientes del mismo autor (≤60s)
        que no fueron capturados (ej: anteriores a una mención) y los incluye,
        y escanea sus enlaces, EXIF y audio si se proporcionan vt_api_key y session."""
        channel_id = message.channel.id

        if self._is_flagged(message.id):
            return

        recent_msgs: list[discord.Message] = []
        now = time.time()
        buf_expiry = now + 300.0
        self._buffered_msg_ids[message.id] = buf_expiry
        logger.debug(f"[BUFFER] add msg {message.id} de {message.author} en #{message.channel}")
        if lookback:
            try:
                cutoff = message.created_at - datetime.timedelta(seconds=60)
                async for msg in message.channel.history(
                    before=message, after=cutoff, limit=15
                ):
                    if (
                        msg.author.id == message.author.id
                        and not msg.author.bot
                        and not self._is_flagged(msg.id)
                        and not self._was_in_buffer(msg.id)
                    ):
                        self._buffered_msg_ids[msg.id] = buf_expiry
                        recent_msgs.append(msg)
                recent_msgs.reverse()
            except Exception:
                pass
            if vt_api_key is not None and session is not None:
                for msg in recent_msgs:
                    try:
                        await self._scan_lookback_msg(msg, vt_api_key, session)
                    except Exception:
                        pass

        async with self._buffer_lock:
            if channel_id in self._msg_buffer:
                info = self._msg_buffer[channel_id]
                if info["user_id"] == message.author.id:
                    info["messages"].append(message)
                    info["task"].cancel()
                    info["task"] = asyncio.create_task(
                        self._buffer_auto_flush(channel_id)
                    )
                    return
                else:
                    old_msgs = self._msg_buffer.pop(channel_id)["messages"]
                    asyncio.create_task(self._process_buffer_async(old_msgs))

            self._msg_buffer[channel_id] = {
                "user_id": message.author.id,
                "messages": [*recent_msgs, message],
                "task": asyncio.create_task(self._buffer_auto_flush(channel_id)),
            }

    async def _scan_lookback_msg(
        self,
        msg: discord.Message,
        vt_api_key: str | None,
        session: aiohttp.ClientSession,
    ):
        """Escanea enlaces, registra multimedia y transcribe audio
        de un mensaje recuperado por lookback."""
        m = Message(msg)

        alert_url, dominio, url = await m.CheckAndAlert(vt_api_key, session)
        if alert_url:
            await self._send_alert(
                msg, "", "⚠️ Enlace sensible (lookback)",
                f"**Dominio:** {dominio}\n**URL:** {url}",
            )

        media_atts = [
            a for a in msg.attachments
            if a.content_type and a.content_type.startswith(("image/", "video/", "file/"))
        ]
        if media_atts:
            files = [await a.to_file() for a in media_atts[:10]]
            await self._send_alert(
                msg, "", f"📁 {len(media_atts)} archivo(s) (lookback)",
                Message._describe_attachments(media_atts),
                file=files,
            )

        for a in msg.attachments:
            if a.content_type and a.content_type.startswith("audio/"):
                result = await m.transcribe_audio(GROQ_CLIENT, member=msg.author, attachment=a)
                if result:
                    _, title, details, audio_file = result
                    await self._send_alert(msg, "", title, details, file=audio_file)

    def _buffer_has_active(self, channel_id: int, user_id: int) -> bool:
        """Chequeo rápido (sin lock) si un usuario tiene buffer activo en un canal."""
        info = self._msg_buffer.get(channel_id)
        return info is not None and info["user_id"] == user_id

    async def _buffer_try_flush(self, message: discord.Message):
        """Intenta flushear el buffer si otro usuario (no el dueño) habla."""
        async with self._buffer_lock:
            info = self._msg_buffer.get(message.channel.id)
            if info is not None and info["user_id"] != message.author.id:
                old_msgs = self._msg_buffer.pop(message.channel.id)["messages"]
                asyncio.create_task(self._process_buffer_async(old_msgs))

    async def _buffer_auto_flush(self, channel_id: int):
        """Flush automático tras 60s de inactividad del usuario."""
        await asyncio.sleep(self._buffer_flush_delay)
        async with self._buffer_lock:
            info = self._msg_buffer.pop(channel_id, None)
        if info is not None:
            await self._process_buffer_async(info["messages"])

    async def _process_buffer_async(self, messages: list[discord.Message]):
        """Procesa el buffer acumulado: analiza todo el texto combinado."""
        if not messages:
            return
        try:
            # Ordenar cronológicamente por created_at
            sorted_msgs = sorted(messages, key=lambda m: m.created_at)

            # Si el texto combinado (sin URLs) es demasiado corto, no merece
            # una llamada a Groq. Esto permite acumular mensajes de 1-2 letras
            # (insultos deletreados) sin gastar llamadas en un "ok" suelto.
            combined_meaningful = "".join(
                Message.meaningful_text(m.content) for m in sorted_msgs
            )
            if len(combined_meaningful) < 3:
                return

            parts = []
            for msg in sorted_msgs:
                ts = msg.created_at.strftime("%H:%M")
                parts.append(f"[{ts}] {msg.content}")
            combined_text = "\n".join(parts)

            last_msg = sorted_msgs[-1]
            msg_obj = Message(last_msg)
            misconduct = await msg_obj.Misconduct(
                GROQ_CLIENT,
                combined_text=combined_text,
                timeout=self.get_config("groq_timeout", 10.0),
            )
            if misconduct:
                code = generate_code()
                now = time.time()
                flag_expiry = now + 120.0
                for m in sorted_msgs:
                    self._flagged_msg_ids[m.id] = flag_expiry
                # Chain log si algún autor no es protegido
                for m in sorted_msgs:
                    member = m.guild.get_member(m.author.id)
                    if member and not discord.utils.get(
                        member.roles, id=self.protected_role_id
                    ):
                        chain_log = get_chain_log()
                        chain_log.add_alert(
                            str(m.author.id),
                            code,
                            "Msg INA. [buffer]",
                            m.jump_url,
                        )
                        break

                alert_text = "\n".join(
                    f"**{m.created_at.strftime('%H:%M')}:** {m.content}"
                    for m in sorted_msgs
                )
                await self._send_alert(
                    last_msg,
                    code,
                    "❗ Mensaje inapropiado (múltiples mensajes)",
                    f"**Contenido acumulado:**\n{alert_text[:950]}",
                )

            await msg_obj._process_overflow(GROQ_CLIENT)
        except Exception as e:
            logger.exception(f"[BUFFER] Error procesando buffer: {e}")

    @asynccontextmanager
    async def _get_session(self):
        if self.http_session:
            yield self.http_session
        else:
            async with aiohttp.ClientSession() as session:
                yield session

    @staticmethod
    def _read_config_file():
        """Lee bot_config.json de forma sincrona. Devuelve dict o None si falla."""
        try:
            if BOT_CONFIG_PATH.exists():
                with BOT_CONFIG_PATH.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                    return {**DEFAULTS, **raw}
        except Exception as e:
            logger.warning(f"[CONFIG] Error leyendo archivo: {e}")
        return None

    @staticmethod
    def _config_hash(cfg: dict) -> str:
        """Hash del contenido para comparar sin depender de mtime."""
        return hashlib.md5(json.dumps(cfg, sort_keys=True).encode()).hexdigest()

    async def _apply_bot_config(self, new_config: dict):
        """Aplica una nueva configuracion y registra los cambios."""
        old = self.bot_config.copy() if self.bot_config else {}

        # Log detallado
        old_det = bool(old.get("detailed_logging", False))
        new_det = bool(new_config.get("detailed_logging", False))
        if old_det != new_det:
            logger.setLevel(logging.DEBUG if new_det else logging.INFO)
            logger.info(
                f"[CONFIG] Logs detallados {'activados' if new_det else 'desactivados'}."
            )

        # Whisper
        old_wh = bool(old.get("enable_whisper", True))
        new_wh = bool(new_config.get("enable_whisper", True))
        whisper_cog = self.get_cog("Whisper")
        if old_wh != new_wh:
            if new_wh and whisper_cog is None:
                # Usar los valores actuales (pueden haber cambiado via /set-data),
                # no el BD global leido al importar el modulo.
                self.add_cog(
                    Whisper(self, (self.staff_channel_id, self.protected_role_id))
                )
                logger.info("[CONFIG] Cog 'Whisper' anadido.")
            elif not new_wh and whisper_cog is not None:
                self.remove_cog("Whisper")
                logger.info("[CONFIG] Cog 'Whisper' eliminado.")

        # Registrar otros cambios
        for key in [
            "log_multimedia",
            "transcribe_audio",
            "log_message_edits",
            "monitor_voice_channels",
            "check_exif_metadata",
        ]:
            old_val = bool(old.get(key, True))
            new_val = bool(new_config.get(key, True))
            if old_val != new_val:
                logger.info(f"[CONFIG] '{key}' cambiado a {new_val}.")

        # Fuente unica de verdad: el estado vive en self.bot_config.
        self.bot_config = new_config

    async def reload_config(self):
        """Recarga manualmente la configuracion desde archivo."""
        cfg = await asyncio.to_thread(self._read_config_file)
        if cfg is not None:
            await self._apply_bot_config(cfg)
            logger.info("[CONFIG] Configuracion recargada manualmente.")
            return True
        return False

    def reload_data(self):
        """Recarga el canal de staff y el rol protegido desde la BD sin reiniciar."""
        row = read_row()
        try:
            new_staff = row[0][0]
            new_role = row[0][1]
        except Exception:
            new_staff, new_role = 0, 0

        self.staff_channel_id = new_staff
        self.protected_role_id = new_role

        whisper_cog = self.get_cog("Whisper")
        if whisper_cog:
            whisper_cog.bd = (new_staff, new_role)

        logger.info(
            f"[RELOAD] Datos recargados: canal={self.staff_channel_id}, "
            f"rol={self.protected_role_id}"
        )

    async def setup_hook(self) -> None:
        try:
            self.http_session = aiohttp.ClientSession()
            logger.info("HTTP client session creada.")
        except Exception as e:
            logger.exception(f"No se pudo crear session HTTP: {e}")

        # Inicializar configuracion desde archivo
        self.bot_config = (
            BOT_CONFIG.copy() if isinstance(BOT_CONFIG, dict) else DEFAULTS.copy()
        )
        logger.info("[SETUP] bot_config inicializado.")

    async def close(self) -> None:
        try:
            if self.http_session:
                await self.http_session.close()
                logger.info("HTTP client session cerrada.")
        finally:
            await super().close()

    async def on_application_command_error(
        self, ctx: discord.ApplicationContext, error: discord.DiscordException
    ) -> None:
        exc = error.original if isinstance(error, discord.ApplicationCommandInvokeError) else error
        if isinstance(exc, discord.HTTPException):
            if exc.code == 10062 or exc.status == 404:
                logger.warning(f"[Cmd] Interaction expirada o invalida: {exc}")
            else:
                logger.error(
                    f"[Cmd] HTTP {exc.status} en {ctx.command.qualified_name if ctx.command else 'desconocido'}: {exc}"
                )
        else:
            logger.error(
                f"[Cmd] Error no manejado en {ctx.command.qualified_name if ctx.command else 'desconocido'}: {exc}"
            )

    async def on_ready(self):
        await self.change_presence(status=discord.Status.invisible)
        logger.info(f"Logged in as {self.user}")

        for guild in self.guilds:
            if guild.id != self.allowed_guild_id:
                logger.warning(
                    f"🚫 Servidor no autorizado detectado al iniciar: {guild.name} ({guild.id}). Abandonando..."
                )
                try:
                    if guild.owner:
                        await guild.owner.send(
                            "Este bot es privado y solo funciona en un servidor autorizado. "
                            "Si crees que esto es un error, contacta al desarrollador."
                        )
                finally:
                    await guild.leave()

    async def on_guild_join(self, guild):
        if guild.id != self.allowed_guild_id:
            logger.warning(
                f"🚫 Bot anadido a servidor no autorizado: {guild.name} ({guild.id}). Abandonando..."
            )
            try:
                if guild.owner:
                    await guild.owner.send(
                        "Este bot es privado y solo funciona en un servidor autorizado. "
                        "Si crees que esto es un error, contacta al desarrollador."
                    )
            finally:
                await guild.leave()
        else:
            logger.info(f"✅ Bot anadido a servidor autorizado: {guild.name}")

    async def _send_alert(self, message_or_text, code, title, details, file=None):
        staff_channel = self.get_channel(self.staff_channel_id)
        if not isinstance(staff_channel, (discord.TextChannel, discord.Thread)):
            logger.error("Canal de staff no valido")
            return

        embed = discord.Embed(title=title, color=0xFF0000)

        if isinstance(message_or_text, discord.Message):
            try:
                user = f"Usuario: {message_or_text.author.mention}"
            except Exception as e:
                logger.exception(f"Error al obtener el nombre del usuario: {e}")
                user = ""

            embed.description = user
            code_str = f"**Code:** {code}" if code else None

            try:
                jump_url = f":mailbox_with_mail: [Ir directamente al mensaje]({message_or_text.jump_url})"
                fk = Krorus._file_kwargs(file)
                if len(message_or_text.content) < 950:
                    embed.add_field(
                        name="Detalles",
                        value=f"{details}\n{jump_url}",
                        inline=False,
                    )
                    await staff_channel.send(code_str, embed=embed, **fk)
                else:
                    embed.add_field(name="", value=jump_url, inline=False)
                    await staff_channel.send(code_str, embed=embed, **fk)
                    await staff_channel.send(details)
                return
            except AttributeError:
                embed.add_field(name="Detalles", value=details, inline=False)
                await staff_channel.send(
                    code_str, embed=embed, **Krorus._file_kwargs(file)
                )
                return
            except Exception as e:
                self._maybe_rate_limit(e)
                logger.exception(f"Error al enviar alerta: {e}")
                return
        else:
            if message_or_text:
                embed.description = str(message_or_text)
            code_str = f"**Code:** {code}" if code else None
            embed.add_field(name="Detalles", value=details, inline=False)
            try:
                await staff_channel.send(
                    code_str, embed=embed, **Krorus._file_kwargs(file)
                )
            except Exception as e:
                self._maybe_rate_limit(e)
                logger.exception(f"Error al enviar alerta sin mensaje: {e}")
            return

    # ── on_message ────────────────────────────────────────────────────────

    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        if not self.check_rate_limit("on_message"):
            return

        if message.guild.id != self.allowed_guild_id:
            logger.warning(
                f"🚫 Servidor no autorizado detectado en on_message: {message.guild.name} ({message.guild.id}). Abandonando..."
            )
            try:
                if message.guild.owner:
                    await message.guild.owner.send(
                        "Este bot es privado y solo funciona en un servidor autorizado. "
                        "Si crees que esto es un error, contacta al desarrollador."
                    )
            finally:
                await message.guild.leave()
            return

        # ── Sala de espera: si otro usuario habla, flushear buffer ──
        await self._buffer_try_flush(message)

        # 1. Respuesta a un mensaje de usuario protegido
        if message.reference:
            logger.info(
                f"[REF] {message.author} responde al mensaje {message.reference.message_id}"
            )
            async with self._get_session() as session:
                vt_api_key = os.getenv("VIRUSTOTAL_API_KEY")
                msg = Message(message)
                results = await msg._ref_message(
                    self.protected_role_id,
                    GROQ_CLIENT,
                    vt_api_key,
                    session,
                    do_misconduct=False,
                )
                if results:
                    for code, alert, details, file in results:
                        await self._send_alert(message, code, alert, details, file)
            if results is not None:
                # Buffer solo si el texto es analizable
                if message.content.strip() and await msg._has_analyzable_text():
                    await self._buffer_add(message, lookback=True, vt_api_key=vt_api_key, session=session)
                return
            # Sin protegido involucrado en el reply → NO retornar: el mensaje
            # puede mencionar a un protegido en el texto (seccion 2) o venir
            # de un autor protegido (seccion 3).

        # 2. Menciones a usuarios protegidos
        if message.mentions:
            logger.info(
                f"[MENTION] {message.author} menciona a: "
                f"{[str(m) for m in message.mentions]}"
            )
            async with self._get_session() as session:
                vt_api_key = os.getenv("VIRUSTOTAL_API_KEY")
                msg = Message(message)
                results = await msg._mention_user(
                    message.mentions,
                    self.protected_role_id,
                    GROQ_CLIENT,
                    vt_api_key,
                    session,
                    do_misconduct=False,
                )
                if results:
                    for code, alert, details, file in results:
                        await self._send_alert(message, code, alert, details, file)
            # Buffer solo si hay un protegido involucrado y el texto es analizable
            if (
                results is not None
                and message.content.strip()
                and await msg._has_analyzable_text()
            ):
                await self._buffer_add(message, lookback=True, vt_api_key=vt_api_key, session=session)

            # Si se mencionó a un protegido, salir (ya procesado)
            if results is not None:
                return

            # No se mencionó a ningún protegido → solo procesar si el autor es protegido
            mention_author = message.author
            if not isinstance(mention_author, discord.Member):
                mention_author = message.guild.get_member(mention_author.id)
            if not mention_author or not discord.utils.get(
                mention_author.roles, id=self.protected_role_id
            ):
                return
            # Autor es protegido → cae a sección 3 para análisis completo

        # 3. Solo se procesa si el autor es un usuario protegido
        member = message.author
        if not isinstance(member, discord.Member):
            member = message.guild.get_member(member.id)
            if not member:
                return

        if not discord.utils.get(member.roles, id=self.protected_role_id):
            # No es protegido, pero si tiene un buffer activo (por mención/reply
            # reciente a un protegido), sus mensajes posteriores también se acumulan
            # y se escanean enlaces, multimedia y audio.
            if self._buffer_has_active(message.channel.id, message.author.id):
                msg = Message(message)
                async with self._get_session() as session:
                    vt_api_key = os.getenv("VIRUSTOTAL_API_KEY")
                    if message.content.strip():
                        alert_url, dominio, url = await msg.CheckAndAlert(vt_api_key, session)
                        if alert_url:
                            await self._send_alert(
                                message, "", "⚠️ Enlace sensible",
                                f"**Dominio:** {dominio}\n**URL:** {url}",
                            )
                    media_atts = [
                        a for a in message.attachments
                        if a.content_type and a.content_type.startswith(("image/", "video/", "file/"))
                    ]
                    if media_atts:
                        files = [await a.to_file() for a in media_atts[:10]]
                        await self._send_alert(
                            message, "", f"📁 {len(media_atts)} archivo(s)",
                            Message._describe_attachments(media_atts),
                            file=files,
                        )
                    for a in message.attachments:
                        if a.content_type and a.content_type.startswith("audio/"):
                            result = await msg.transcribe_audio(
                                GROQ_CLIENT, member=member, attachment=a
                            )
                            if result:
                                _, title, details, audio_file = result
                                await self._send_alert(
                                    message, "", title, details, file=audio_file,
                                )
                if message.content.strip() and await msg._has_analyzable_text():
                    await self._buffer_add(message)
            return

        ignore_cog = self.get_cog("AppendIgnoreWord")
        if ignore_cog and ignore_cog.should_ignore(message.content):
            return

        msg = Message(message)

        # Escaneo de enlaces
        async with self._get_session() as session:
            vt_api_key = os.getenv("VIRUSTOTAL_API_KEY")
            alert_url, dominio, url = await msg.CheckAndAlert(vt_api_key, session)

        if alert_url:
            await self._send_alert(
                message,
                "",
                "⚠️ Enlace sensible",
                f"**Dominio:** {dominio}\n**URL:** {url}",
            )

        # Sala de espera: acumular texto para análisis por lotes con Groq.
        # min_len=1: los mensajes muy cortos ("p", "u", "t", "o") también se
        # acumulan para detectar insultos deletreados en varios mensajes; el
        # buffer descarta al final los lotes sin contenido suficiente.
        if message.content.strip() and await msg._has_analyzable_text(min_len=1):
            await self._buffer_add(message)

        # Manejo de archivos adjuntos
        if message.attachments:
            if not self.get_config("log_multimedia", True):
                logger.debug("[CONFIG] Registro de multimedia deshabilitado.")
                return

            media_atts = []
            for att in message.attachments:
                ct = (att.content_type or "").lower()
                logger.info(f"[EXIF] Attachment: {att.filename}, content_type: {ct}")

                if ct.startswith("audio/"):
                    if self.get_config("transcribe_audio", True):
                        result = await msg.transcribe_audio(
                            GROQ_CLIENT,
                            message.author,
                            timeout=self.get_config("groq_audio_timeout", 30.0),
                            attachment=att,
                        )
                        if result:
                            code, title, details, audio_file = result
                            await self._send_alert(
                                message, code, title, details, file=audio_file
                            )
                elif ct.startswith(("image/", "video/", "file/")) or ct.startswith(
                    "application/"
                ):
                    media_atts.append(att)

            logger.info(
                f"[EXIF] Attachments: {len(message.attachments)}, Media: {len(media_atts)}"
            )

            if media_atts:
                if self.get_config("check_exif_metadata", True):
                    for att in media_atts:
                        logger.info(
                            f"[EXIF] Checking: {att.filename}, content_type: {att.content_type}"
                        )
                        exif_report = await msg.check_exif_sensible(att)
                        if exif_report and exif_report.has_sensitive_data:
                            risk_level = (
                                "🚨 ALTO RIESGO"
                                if exif_report.has_high_risk
                                else "⚠️ Riesgo"
                            )
                            await self._send_alert(
                                message,
                                "",
                                f"🔍 {risk_level}: EXIF sensible detectado",
                                exif_report.summary(),
                            )

                files_discord = [await att.to_file() for att in media_atts[:10]]
                descripcion = Message._describe_attachments(media_atts)
                await self._send_alert(
                    message,
                    "",
                    f"📁 {len(media_atts)} archivo(s) detectado(s)",
                    descripcion,
                    file=files_discord,
                )
            return

    # ── on_message_edit ───────────────────────────────────────────────────

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot:
            return

        if not after.guild or after.guild.id != self.allowed_guild_id:
            return

        if before.content == after.content:
            return

        if not self.get_config("log_message_edits", True):
            logger.debug("[CONFIG] Registro de mensajes editados deshabilitado.")
            return

        member = after.guild.get_member(after.author.id)
        if not member:
            return

        author_is_protected = bool(
            discord.utils.get(member.roles, id=self.protected_role_id)
        )

        mentions_protected = any(
            discord.utils.get(getattr(m, "roles", []), id=self.protected_role_id)
            for m in after.mentions
            if m.id != after.author.id
        )

        replies_to_protected = False
        if after.reference:
            resolved = getattr(after.reference, "resolved", None)
            if isinstance(resolved, discord.Message):
                ref_roles = getattr(resolved.author, "roles", [])
                replies_to_protected = any(
                    r.id == self.protected_role_id for r in ref_roles
                )

        if not replies_to_protected and after.reference and after.reference.message_id:
            try:
                ref_msg = await after.channel.fetch_message(after.reference.message_id)
                ref_roles = getattr(ref_msg.author, "roles", [])
                replies_to_protected = any(
                    r.id == self.protected_role_id for r in ref_roles
                )
            except discord.NotFound:
                pass

        if not (author_is_protected or mentions_protected or replies_to_protected or self._was_in_buffer(after.id)):
            return

        await self._send_alert(
            after,
            "",
            "📝 Mensaje editado",
            f"**Antes:**\n```{before.content[:950]}```\n**Después:**\n```{after.content[:950]}```",
        )

        if self._was_in_buffer(after.id):
            logger.info(
                f"[EDIT] El mensaje {after.id} estuvo en el buffer — "
                f"edición puede extender contexto previo."
            )

        if not author_is_protected and after.content.strip():
            msg_obj = Message(after)
            misconduct = await msg_obj.Misconduct(
                GROQ_CLIENT,
                timeout=self.get_config("groq_timeout", 10.0),
            )
            if misconduct:
                code = generate_code()
                self._flagged_msg_ids[after.id] = time.time() + 120.0
                chain_log = get_chain_log()
                chain_log.add_alert(
                    str(after.author.id), code, "Msg INA. [edited]", after.jump_url
                )
                await self._send_alert(
                    after,
                    code,
                    "❗ Contenido inapropiado (edicion)",
                    f"**Contenido editado:**\n```{after.content[:950]}```",
                )

            await msg_obj._process_overflow(GROQ_CLIENT)

    # ── on_voice_state_update ─────────────────────────────────────────────

    VOICE_ALERT_COOLDOWN = 300  # segundos entre alertas repetidas por canal

    async def check_voice_channel(self, channel, target_role_id: int):
        """Alerta si en `channel` conviven protegidos y no-protegidos.

        Aplica un cooldown por canal para no spamear al staff con la misma
        situacion en cada join/leave. El cooldown se limpia cuando la
        situacion se resuelve, para que una nueva ocurrencia alerte al instante.
        """
        if channel is None:
            return

        members = [m for m in channel.members if not m.bot]
        protegidos = [
            m for m in members if discord.utils.get(m.roles, id=target_role_id)
        ]
        others = [
            m for m in members if not discord.utils.get(m.roles, id=target_role_id)
        ]

        if not protegidos or not others:
            self._voice_alert_cooldown.pop(channel.id, None)
            return

        now = time.time()
        last = self._voice_alert_cooldown.get(channel.id, 0)
        if now - last < self.VOICE_ALERT_COOLDOWN:
            return
        self._voice_alert_cooldown[channel.id] = now

        await self._send_alert(
            f"Se ha detectado una situacion de supervision en el canal **{channel.mention}**.",
            "",
            "⚠️ Alerta de supervision en canal de voz",
            f"**Protegidos:**\n{', '.join(m.mention for m in protegidos)}\n_ _\n**Miembros:**\n{', '.join(m.mention for m in others)}",
        )

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        if before.channel != after.channel:
            if after.channel:
                logger.info(f"{member.display_name} se unio a {after.channel.name}")
            elif before.channel:
                logger.info(f"{member.display_name} salio de {before.channel.name}")

            if self.get_config("monitor_voice_channels", True):
                # Solo los canales afectados por el evento, no todo el guild
                await self.check_voice_channel(after.channel, self.protected_role_id)
                await self.check_voice_channel(before.channel, self.protected_role_id)


def main() -> None:
    client = Krorus()

    if BOT_CONFIG.get("enable_whisper", True):
        client.add_cog(Whisper(client, BD))
    else:
        logger.info("Cog 'Whisper' deshabilitado por la configuracion del proyecto.")

    client.add_cog(AppendAlertDomain(client))
    client.add_cog(AppendWhitelistDomain(client))
    client.add_cog(SetData(client))
    client.add_cog(ListUsers(client))
    client.add_cog(CheckUser(client))
    client.add_cog(AppendIgnoreWord(client, PATH_IGNORE_WORDS))
    client.add_cog(HealthCheck(client))
    client.add_cog(ExifCheck(client))

    try:
        client.run(os.getenv("TOKEN"))
    except Exception as e:
        logger.exception(f"Unhandled error while running bot: {e}")
