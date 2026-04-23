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
from .modules.audio import transcribe_audio
from .modules.code import generate_code
from .modules.database import try_read_row
from .modules.logs import Logs
from .modules.message import Message

load_dotenv()

GROQ_CLIENT = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
BD = try_read_row()
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
                    # Intentar notificar al owner
                    if guild.owner:
                        await guild.owner.send(
                            "Este bot es privado y solo funciona en un servidor autorizado. "
                            "Si crees que esto es un error, contacta al desarrollador."
                        )
                finally:
                    await guild.leave()

    async def on_guild_join(self, guild):
        if guild.id != self.ALLOWED_GUILD_ID:
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

    async def _send_alert(
        self, message, code, title, details
    ):  # Este metodo es la estructura para enviar alertas al canal de staff

        staff_channel_id = BD[0]
        staff_channel = self.get_channel(staff_channel_id)
        if not isinstance(staff_channel, discord.TextChannel):
            print("Canal de staff no válido")
            return

        try:
            USER = f"Usuario: {message.author.mention}"
        except Exception as e:
            print(f"Error al obtener el nombre del usuario: {e}")
            USER = ""

        embed = discord.Embed(
            title=title,
            description=f"{USER}",
            color=0xFF0000,
        )

        try:
            URL = (
                f":mailbox_with_mail: [Ir directamente al mensaje]({message.jump_url})"
            )
        except Exception as e:
            print(f"Error al obtener URL: {e}")
            URL = ""

        embed.add_field(
            name="Detalles",
            value=f"{details}\n{URL}",
            inline=False,
        )

        code_ = f"**Code:** {code}" if code else ""

        await staff_channel.send(code_, embed=embed)
        print("Alerta enviada")

    async def on_message(self, message):
        if message.author.bot:  # Si el mensaje es de un bot, no hacemos nada
            return

        if (
            message.guild.id != self.allowed_guild_id
        ):  # Si el mensaje no es de un servidor autorizado, salimos del servidor
            await message.guild.leave()
            return

        if not message.guild:  # Si el mensaje no es de un servidor, no hacemos nada
            return

        ignore_cog = self.get_cog("AppendIgnoreWord")
        if ignore_cog and ignore_cog.should_ignore(
            message.content
        ):  # Si el mensaje debe ser ignorado, no hacemos nada
            return

        if (
            len(message.content) <= 2
        ):  # Si el mensaje es demasiado corto, no hacemos nada
            return

        if message.reference:
            try:
                ref_message = await message.channel.fetch_message(
                    message.reference.message_id
                )

                if ref_message.author == self.user:
                    return

                if any(map(lambda r: r.id == BD[1], ref_message.author.roles)):
                    if message.attachments:
                        await transcribe_audio(
                            self, message, GROQ_CLIENT, ref_message.author
                        )
                        return

                    msg = Message(message.content)

                    misconduct = await msg.Misconduct(GROQ_CLIENT)
                    if misconduct:
                        code = generate_code()
                        if not discord.utils.get(
                            message.author.roles, id=BD[1]
                        ):  # Si el usuario no tiene el rol necesario, no hacemos nada
                            logs = Logs()
                            logs.addAlert(
                                message.author.id,
                                code,
                                f"Msg INA. [to {ref_message.author.mention}]",
                                message.jump_url,
                            )

                        await self._send_alert(
                            message,
                            code,
                            "❗ Mensaje inapropiado",
                            f"Dicho a: {ref_message.author.mention}\n**Contenido:**\n```{message.content}```",
                        )
                    return

            except discord.NotFound:
                return

        if ids := re.findall(r"<@!?(\d+)>", message.content):
            members = [
                discord.utils.get(message.guild.members, id=int(m)) for m in ids
            ]  # Se obtiene los miembros mencionados

            for member in members:
                if any(map(lambda r: r.id == BD[1], member.roles)):
                    msg = Message(message.content)

                    misconduct = await msg.Misconduct(GROQ_CLIENT)
                    if misconduct:
                        code = generate_code()

                        if not discord.utils.get(
                            member.roles, id=BD[1]
                        ):  # Si el usuario no tiene el rol necesario, no hacemos nada
                            logs = Logs()
                            logs.addAlert(
                                message.author.id,
                                code,
                                "Msg INA. [Protect M.]",
                                message.jump_url,
                            )

                        await self._send_alert(
                            message,
                            code,
                            "❗ Mensaje inapropiado",
                            f"Protegidos mencionados: {', '.join([m.mention for m in members if discord.utils.get(m.roles, id=BD[1])])}\n**Contenido:**\n```{message.content}```",
                        )
                    return

        member = message.author
        if not isinstance(member, discord.Member):
            member = message.guild.get_member(member.id)
            if not member:  # Si el mensaje es de un usuario, intentamos obtener su rol en el servidor
                return

        if not discord.utils.get(
            member.roles, id=BD[1]
        ):  # Si el usuario no tiene el rol necesario, no hacemos nada
            return

        msg = Message(message.content)

        async with aiohttp.ClientSession() as session:
            vt_api_key = os.getenv("VIRUSTOTAL_API_KEY")
            alert_url, dominio, url = await msg.CheckAndAlert(vt_api_key, session)

        if alert_url:
            await self._send_alert(
                message, "⚠️ Enlace sensible", f"**Dominio:** {dominio}\n**URL:** {url}"
            )
            return

        misconduct = await msg.Misconduct(GROQ_CLIENT)
        if misconduct:
            await self._send_alert(
                message,
                "❗ Mensaje inapropiado",
                f"**Contenido:**\n```{message.content}```",
            )

        if message.attachments:
            await transcribe_audio(self, message, GROQ_CLIENT)
            return

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot:
            return

        if before.content != after.content:
            await self._send_alert(
                after,
                "📝 Mensaje editado",
                f"**Antes:**\n```{before.content}```\n**Después:**\n```{after.content}```",
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

            # Si hay al menos un miembro con el rol y otro sin el rol, se activa la alerta
            if members_with_role and members_without_role:
                await self._send_alert(
                    f"Se ha detectado una situación de supervisión en el canal **{vc.mention}**.",
                    "⚠️ Alerta de supervisión en canal de voz",
                    f"Protegidos: {', '.join([m.mention for m in members_with_role]) or 'Ninguno'}\nMiembros: {', '.join([m.mention for m in members_without_role]) or 'Ninguno'}",
                )

    # Evento para monitorear cambios en los canales de voz
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        # IDs de los roles (ajústalo según tu configuración)
        ROLE_PROTEGIDO_ID = BD[1]  # Reemplaza con el ID real

        # Determinar si el miembro ha entrado o salido de un canal de voz
        if before.channel != after.channel:
            if after.channel:
                print(f"{member.display_name} se unió a {after.channel.name}")
            elif before.channel:
                print(f"{member.display_name} salió de {before.channel.name}")

            await self.check_voice_channels(member.guild, ROLE_PROTEGIDO_ID)


client = Krorus()


def main() -> None:
    client.add_cog(Whisper(client, BD))
    client.add_cog(AppendAlertDomain(client))
    client.add_cog(AppendWhitelistDomain(client))
    client.add_cog(SetData(client))
    client.add_cog(ListUsers(client))
    client.add_cog(CheckUser(client))
    client.add_cog(AppendIgnoreWord(client, PATH_IGNORE_WORDS))

    client.run(os.getenv("TOKEN"))
