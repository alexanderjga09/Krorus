import asyncio
import hashlib
import json
import logging
import os
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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("krorus")

GROQ_CLIENT = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

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
        super().__init__(intents=discord.Intents.all())
        self.allowed_guild_id = int(os.getenv("ALLOWED_GUILD_ID", "0"))
        self.http_session: aiohttp.ClientSession | None = None
        self.bot_config: dict = {}
        self._rate_limit_until: float = 0
        self._rate_limit_retry_after: int = 60

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
        if time.time() < self._rate_limit_until:
            logger.warning(f"[RATE LIMIT] {action}: bloqueado hasta {self._rate_limit_until}")
            return False
        return True

    def set_rate_limit(self, seconds: int, reason: str = ""):
        """Activa rate limit por X segundos."""
        self._rate_limit_until = time.time() + seconds
        logger.warning(f"[RATE LIMIT] Activado por {seconds}s: {reason}")

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
                self.add_cog(Whisper(self, BD))
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
        ]:
            old_val = bool(old.get(key, True))
            new_val = bool(new_config.get(key, True))
            if old_val != new_val:
                logger.info(f"[CONFIG] '{key}' cambiado a {new_val}.")

        # Actualizar fuente unica
        self.bot_config = new_config
        # Tambien actualizar global para compatibilidad
        global BOT_CONFIG
        BOT_CONFIG = new_config

    async def reload_config(self):
        """Recarga manualmente la configuracion desde archivo."""
        cfg = await asyncio.to_thread(self._read_config_file)
        if cfg is not None:
            await self._apply_bot_config(cfg)
            logger.info("[CONFIG] Configuracion recargada manualmente.")
            return True
        return False

    def reload_data(self):
        """Recarga STAFF_CHANNEL_ID y PROTECTED_ROLE_ID desde la BD sin reiniciar."""
        global STAFF_CHANNEL_ID, PROTECTED_ROLE_ID
        row = read_row()
        # read_row devuelve una lista de tuplas, por ejemplo [(staff_channel, role_id)]
        try:
            STAFF_CHANNEL_ID = row[0][0]
            PROTECTED_ROLE_ID = row[0][1]
        except Exception:
            STAFF_CHANNEL_ID, PROTECTED_ROLE_ID = 0, 0
        logger.info(
            f"[RELOAD] Datos recargados: canal={STAFF_CHANNEL_ID}, rol={PROTECTED_ROLE_ID}"
        )

    async def setup_hook(self) -> None:
        try:
            self.http_session = aiohttp.ClientSession()
            logger.info("HTTP client session creada.")
        except Exception as e:
            logger.exception(f"No se pudo crear session HTTP: {e}")

        # Inicializar configuracion desde archivo
        self.bot_config = BOT_CONFIG.copy() if isinstance(BOT_CONFIG, dict) else DEFAULTS.copy()
        logger.info("[SETUP] bot_config inicializado.")

    async def close(self) -> None:
        try:
            if self.http_session:
                await self.http_session.close()
                logger.info("HTTP client session cerrada.")
        finally:
            await super().close()

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
        staff_channel = self.get_channel(STAFF_CHANNEL_ID)
        if not isinstance(staff_channel, discord.TextChannel):
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

        # 1. Respuesta a un mensaje de usuario protegido
        if message.reference:
            logger.info(
                f"[REF] {message.author} responde al mensaje {message.reference.message_id}"
            )
            async with self._get_session() as session:
                vt_api_key = os.getenv("VIRUSTOTAL_API_KEY")
                msg = Message(message)
                results = await msg._ref_message(
                    PROTECTED_ROLE_ID,
                    GROQ_CLIENT,
                    vt_api_key,
                    session,
                )
                if results:
                    for code, alert, details, file in results:
                        await self._send_alert(message, code, alert, details, file)
            return

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
                    PROTECTED_ROLE_ID,
                    GROQ_CLIENT,
                    vt_api_key,
                    session,
                )
                if results:
                    for code, alert, details, file in results:
                        await self._send_alert(message, code, alert, details, file)
            return

        # 3. Solo se procesa si el autor es un usuario protegido
        member = message.author
        if not isinstance(member, discord.Member):
            member = message.guild.get_member(member.id)
            if not member:
                return

        if not discord.utils.get(member.roles, id=PROTECTED_ROLE_ID):
            return

        ignore_cog = self.get_cog("AppendIgnoreWord")
        if ignore_cog and ignore_cog.should_ignore(message.content):
            return

        if len(message.content) <= 2 and not (
            message.attachments
            and message.attachments[0].content_type
            and (
                message.attachments[0].content_type.startswith("audio/")
                or message.attachments[0].content_type.startswith("image/")
                or message.attachments[0].content_type.startswith("video/")
                or message.attachments[0].content_type.startswith("file/")
            )
        ):
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

        # Análisis de misconduct
        misconduct = await msg.Misconduct(GROQ_CLIENT)
        if misconduct:
            await self._send_alert(
                message,
                "",
                "❗ Mensaje inapropiado",
                f"**Contenido:**\n```{message.content}```",
            )

        # Manejo de archivos adjuntos
        if message.attachments:

            if not self.get_config("log_multimedia", True):
                logger.debug("[CONFIG] Registro de multimedia deshabilitado.")
                return

            for att in message.attachments:
                if att.content_type and att.content_type.startswith("audio/"):
                    if self.get_config("transcribe_audio", True):
                        result = await msg.transcribe_audio(GROQ_CLIENT, message.author)
                        if result:
                            code, title, details, audio_file = result
                            await self._send_alert(
                                message, code, title, details, file=audio_file
                            )

            media_atts = [
                att
                for att in message.attachments
                if att.content_type
                and att.content_type.startswith(("image/", "video/", "file/"))
            ]
            if media_atts:
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
            discord.utils.get(member.roles, id=PROTECTED_ROLE_ID)
        )

        mentions_protected = any(
            discord.utils.get(getattr(m, "roles", []), id=PROTECTED_ROLE_ID)
            for m in after.mentions
            if m.id != after.author.id
        )

        replies_to_protected = False
        if after.reference:
            resolved = getattr(after.reference, "resolved", None)
            if isinstance(resolved, discord.Message):
                ref_roles = getattr(resolved.author, "roles", [])
                replies_to_protected = any(r.id == PROTECTED_ROLE_ID for r in ref_roles)

        if not replies_to_protected and after.reference and after.reference.message_id:
            try:
                ref_msg = await after.channel.fetch_message(after.reference.message_id)
                ref_roles = getattr(ref_msg.author, "roles", [])
                replies_to_protected = any(r.id == PROTECTED_ROLE_ID for r in ref_roles)
            except discord.NotFound:
                pass

        if not (author_is_protected or mentions_protected or replies_to_protected):
            return

        await self._send_alert(
            after,
            "",
            "📝 Mensaje editado",
            f"**Antes:**\n```{before.content[:950]}```\n**Después:**\n```{after.content[:950]}```",
        )

        if not author_is_protected and after.content.strip():
            msg_obj = Message(after)
            misconduct = await msg_obj.Misconduct(GROQ_CLIENT)
            if misconduct:
                code = generate_code()
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

    # ── on_voice_state_update ─────────────────────────────────────────────

    async def check_voice_channels(self, guild: discord.Guild, target_role_id: int):
        for vc in guild.voice_channels:
            members_in_vc = vc.members
            members_with_role = [
                m
                for m in members_in_vc
                if discord.utils.get(m.roles, id=target_role_id)
            ]
            members_without_role = [
                m
                for m in members_in_vc
                if not discord.utils.get(m.roles, id=target_role_id)
            ]

            if members_with_role and members_without_role:
                await self._send_alert(
                    f"Se ha detectado una situacion de supervision en el canal **{vc.mention}**.",
                    "",
                    "⚠️ Alerta de supervision en canal de voz",
                    f"**Protegidos:**\n{', '.join([m.mention for m in members_with_role]) or 'Ninguno'}\n_ _\n**Miembros:**\n{', '.join([m.mention for m in members_without_role]) or 'Ninguno'}",
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
                await self.check_voice_channels(member.guild, PROTECTED_ROLE_ID)


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

    try:
        client.run(os.getenv("TOKEN"))
    except Exception as e:
        logger.exception(f"Unhandled error while running bot: {e}")
