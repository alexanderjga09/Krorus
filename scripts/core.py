import os
import re
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
from .cogs.list_users import ListUsers
from .cogs.set_data import SetData
from .cogs.whisper import Whisper
from .modules.database import try_read_row
from .modules.message import Message

load_dotenv()

GROQ_CLIENT = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

# Leer configuración de BD y validar
BD = try_read_row()
STAFF_CHANNEL_ID = BD[0]
PROTECTED_ROLE_ID = BD[1]

# Aviso si los datos no están configurados
if not STAFF_CHANNEL_ID or not PROTECTED_ROLE_ID:
    print(
        "⚠️ ADVERTENCIA: STAFF_CHANNEL_ID o PROTECTED_ROLE_ID no están configurados en la base de datos."
    )

PATH_IGNORE_WORDS = Path(__file__).parent.parent / "data" / "ignorewords.json"


class Krorus(commands.Bot):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.allowed_guild_id = int(os.getenv("ALLOWED_GUILD_ID", "0"))

    async def on_ready(self):
        await self.change_presence(status=discord.Status.invisible)
        print(f"Logged in as {self.user}")

        for guild in self.guilds:
            if guild.id != self.allowed_guild_id:
                print(
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
        # Corregido el nombre de la variable (todo minúsculas)
        if guild.id != self.allowed_guild_id:
            print(
                f"🚫 Bot añadido a servidor no autorizado: {guild.name} ({guild.id}). Abandonando..."
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
            print(f"✅ Bot añadido a servidor autorizado: {guild.name}")

    async def _send_alert(self, message_or_text, code, title, details):
        """
        Envía una alerta al canal de staff.
        Acepta un objeto discord.Message, una cadena de texto (para alertas sin mensaje, como canales de voz)
        o None.
        """
        staff_channel = self.get_channel(STAFF_CHANNEL_ID)
        if not isinstance(staff_channel, discord.TextChannel):
            print("Canal de staff no válido")
            return

        embed = discord.Embed(title=title, color=0xFF0000)

        if isinstance(message_or_text, discord.Message):
            # Alerta basada en un mensaje del chat
            try:
                user = f"Usuario: {message_or_text.author.mention}"
            except Exception as e:
                print(f"Error al obtener el nombre del usuario: {e}")
                user = ""

            embed.description = user
            code_str = f"**Code:** {code}" if code else ""

            try:
                jump_url = f":mailbox_with_mail: [Ir directamente al mensaje]({message_or_text.jump_url})"
                if len(message_or_text.content) < 950:
                    embed.add_field(
                        name="Detalles",
                        value=f"{details}\n{jump_url}",
                        inline=False,
                    )
                    await staff_channel.send(code_str, embed=embed)
                else:
                    embed.add_field(name="", value=jump_url, inline=False)
                    await staff_channel.send(code_str, embed=embed)
                    await staff_channel.send(details)
            except AttributeError:
                embed.add_field(name="Detalles", value=details, inline=False)
                await staff_channel.send(code_str, embed=embed)
        else:
            # Alerta sin mensaje (p.ej. supervisión de voz)
            if message_or_text:
                embed.description = str(message_or_text)
            code_str = f"**Code:** {code}" if code else ""
            embed.add_field(name="Detalles", value=details, inline=False)
            await staff_channel.send(code_str, embed=embed)

    async def on_message(self, message):
        if message.author.bot:
            return

        if message.guild.id != self.allowed_guild_id:
            await message.guild.leave()
            return

        if not message.guild:
            return

        # Ignorar palabras configuradas
        ignore_cog = self.get_cog("AppendIgnoreWord")
        if ignore_cog and ignore_cog.should_ignore(message.content):
            return

        # 1. Respuesta a un mensaje de usuario protegido
        if message.reference:
            msg = Message(message)
            result = await msg._ref_message(PROTECTED_ROLE_ID, GROQ_CLIENT)
            if result is not None:
                code, alert, details = result
                await self._send_alert(message, code, alert, details)
            return

        # 2. Menciones a usuarios protegidos
        if ids := re.findall(r"<@!?(\d+)>", message.content):
            msg = Message(message)
            result = await msg._mention_user(ids, PROTECTED_ROLE_ID, GROQ_CLIENT)
            if result is not None:
                code, alert, details = result
                await self._send_alert(message, code, alert, details)
            return

        # 3. A partir de aquí, solo se procesa si el autor es un usuario protegido
        member = message.author
        if not isinstance(member, discord.Member):
            member = message.guild.get_member(member.id)
            if not member:
                return

        if not discord.utils.get(member.roles, id=PROTECTED_ROLE_ID):
            return

        # Ahora sí ignoramos mensajes demasiado cortos (pero no si tiene adjuntos de audio)
        if len(message.content) <= 2 and not (
            message.attachments
            and message.attachments[0].content_type
            and message.attachments[0].content_type.startswith("audio/")
        ):
            return

        # El mensaje viene de un usuario protegido
        msg = Message(message)

        # Escaneo de enlaces con VirusTotal
        async with aiohttp.ClientSession() as session:
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

        # Transcripción de audio (si hay adjuntos de voz)
        if message.attachments:
            att = message.attachments[0]
            if att.content_type and att.content_type.startswith("audio/"):
                result = await msg.transcribe_audio(GROQ_CLIENT, message.author)
                if result:
                    code, title, details = result
                    await self._send_alert(message, code, title, details)
                return

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot:
            return

        if before.content != after.content:
            await self._send_alert(
                after,
                "",
                "📝 Mensaje editado",
                f"**Antes:**\n```{before.content[:950]}```\n**Después:**\n```{after.content[:950]}```",
            )

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
                    f"Se ha detectado una situación de supervisión en el canal **{vc.mention}**.",
                    "",
                    "⚠️ Alerta de supervisión en canal de voz",
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
                print(f"{member.display_name} se unió a {after.channel.name}")
            elif before.channel:
                print(f"{member.display_name} salió de {before.channel.name}")

            await self.check_voice_channels(member.guild, PROTECTED_ROLE_ID)


def main() -> None:
    client = Krorus()

    client.add_cog(Whisper(client, BD))
    client.add_cog(AppendAlertDomain(client))
    client.add_cog(AppendWhitelistDomain(client))
    client.add_cog(SetData(client))
    client.add_cog(ListUsers(client))
    client.add_cog(CheckUser(client))
    client.add_cog(AppendIgnoreWord(client, PATH_IGNORE_WORDS))

    client.run(os.getenv("TOKEN"))
