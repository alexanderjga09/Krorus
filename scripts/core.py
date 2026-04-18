import io
import json as js
import os

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from groq import AsyncGroq, Groq

from .modules.database import createDB, createTable, insertRow, readRow
from .modules.fernet import decrypt_message, encrypt_message
from .modules.message import Message

load_dotenv()

GROQ_CLIENT_AUDIO = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
GROQ_CLIENT = Groq(api_key=os.environ.get("GROQ_API_KEY"))


def try_read_row():
    try:
        return readRow()[0]
    except Exception:
        createDB()
        createTable()
        return None


class Krorus(commands.Bot):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())

    async def on_ready(self):
        await self.change_presence(status=discord.Status.invisible)
        print(f"Logged in as {self.user}")

    async def _send_alert(
        self, message, title, details
    ):  # Este metodo es la estructura para enviar alertas al canal de staff
        BD = try_read_row()
        if not BD:
            return

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
            URL = message.jump_url
        except Exception as e:
            print(f"Error al obtener URL: {e}")
            URL = None

        embed.add_field(
            name="Detalles",
            value=f"{details}\n:mailbox_with_mail: [Ir directamente al mensaje]({URL})",
            inline=False,
        )

        await staff_channel.send(embed=embed)
        print("Alerta enviada")

    async def on_message(self, message):
        BD = try_read_row()
        if not BD:
            return

        if (
            message.author == self.user
        ):  # Si el mensaje es del bot mismo, no hacemos nada
            return

        if not message.guild:  # Si el mensaje no es de un servidor, no hacemos nada
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
            audio_attachment = message.attachments[0]
            # Verifica que sea un formato de audio soportado (mp3, wav, ogg, etc.)
            if any(
                audio_attachment.filename.lower().endswith(fmt)
                for fmt in [".mp3", ".wav", ".ogg", ".m4a", ".flac"]
            ):
                # Lee el archivo de audio de forma asíncrona
                audio_bytes = await audio_attachment.read()

                try:
                    # Prepara el archivo en memoria para enviarlo a Groq
                    audio_file = io.BytesIO(audio_bytes)
                    audio_file.name = (
                        audio_attachment.filename
                    )  # Asigna un nombre, es requerido

                    # Realiza la transcripción de forma asíncrona
                    transcription = await GROQ_CLIENT_AUDIO.audio.transcriptions.create(
                        file=audio_file,  # El archivo en memoria
                        model="whisper-large-v3-turbo",  # Modelo de Groq para transcribir
                        response_format="text",  # Formato de la respuesta (texto plano)
                    )

                    # Envía la transcripción al canal de staff
                    await self._send_alert(
                        message,
                        "📝 Transcripción de audio",
                        f"**Contenido del mensaje de voz:**\n```{transcription}```",
                    )

                except Exception as e:
                    print(f"Error al transcribir el audio: {e}")
                    await self._send_alert(
                        message,
                        "❌ Error de transcripción",
                        f"No se pudo transcribir el audio: {str(e)}",
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
                    f"Miembros con el rol: {', '.join([m.mention for m in members_with_role]) or 'Ninguno'}\nMiembros sin el rol: {', '.join([m.mention for m in members_without_role]) or 'Ninguno'}",
                )

    # Evento para monitorear cambios en los canales de voz
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        BD = try_read_row()
        if not BD:
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


class DecryptButton(discord.ui.View):
    def __init__(self, encrypted_message: str, recipient_id: int):
        super().__init__(timeout=180)
        self.encrypted_message = encrypted_message
        self.recipient_id = recipient_id

    @discord.ui.button(label="🔓 Descifrar Mensaje", style=discord.ButtonStyle.primary)
    async def decrypt_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        if interaction.user.id != self.recipient_id:
            await interaction.response.send_message(
                "❌ No tienes permiso para descifrar este mensaje.", ephemeral=True
            )
            return

        try:
            decrypted_text = decrypt_message(self.encrypted_message, self.recipient_id)
            await interaction.response.send_message(
                f"**Mensaje secreto:**\n{decrypted_text}", ephemeral=True
            )
            button.disabled = True
            await interaction.edit_original_response(view=self)
        except Exception:
            await interaction.response.send_message(
                "❌ Error al descifrar el mensaje. Puede que la clave sea incorrecta o el mensaje esté dañado.",
                ephemeral=True,
            )


@client.slash_command(
    name="whisper", description="Envía un mensaje secreto a un usuario."
)
async def whisper(
    ctx: discord.ApplicationContext,
    destinatario: discord.Option(
        discord.SlashCommandOptionType.user, "El usuario que podrá leer el mensaje."
    ),  # type: ignore
    mensaje: discord.Option(str, "El mensaje secreto que quieres enviar."),  # type: ignore
):
    if destinatario is None:
        destinatario = ctx.author

    BD = try_read_row()
    if not BD:
        return

    encrypted_msg = encrypt_message(mensaje, destinatario.id)
    view = DecryptButton(encrypted_msg, destinatario.id)

    ROLE_PROTEGIDO_ID = BD[1]

    if ROLE_PROTEGIDO_ID in map(
        lambda role: role.id, ctx.author.roles
    ) or ROLE_PROTEGIDO_ID in map(lambda role: role.id, destinatario.roles):
        await client._send_alert(
            ctx,
            "Mensaje secreto",
            f"**Destinatario:** {destinatario.mention}\n```{mensaje}```",
        )

    embed = discord.Embed(
        title="🔒 ¡Tienes un mensaje secreto!",
        description=f"**Remitente:** {ctx.author.mention}\nHaz clic en el botón para leerlo. Este enlace expirará en 3 minutos.",
        color=discord.Color.blue(),
    )

    try:
        await destinatario.send(embed=embed, view=view)
        await ctx.respond(
            f"✅ Mensaje secreto enviado a {destinatario.mention}.", ephemeral=True
        )
    except discord.Forbidden:
        await ctx.respond(
            f"❌ No puedo enviar mensajes directos a {destinatario.mention}. Asegúrate de que sus DMs estén abiertos.",
            ephemeral=True,
        )


@client.slash_command(name="append-alertdomain", description="placeholder")
async def AAD(interaction: discord.Interaction, domain: str):
    with open("scripts/alert_domains.json", "r") as f:
        data = js.load(f)

    data.append(domain)
    with open("scripts/alert_domains.json", "w") as f:
        js.dump(data, f, indent=4)

    await interaction.response.send_message(
        f"Dominio **{domain}** agregado a la lista de alertas"
    )


@client.slash_command(name="set-data", description="")
async def set_data(
    interaction: discord.Interaction,
    staff_channel: discord.TextChannel,
    role_protect: discord.Role,
):
    insertRow(staff_channel.id, role_protect.id)
    await interaction.response.send_message("✅ Datos guardados correctamente.")


def main():
    client.run(os.getenv("TOKEN"))
