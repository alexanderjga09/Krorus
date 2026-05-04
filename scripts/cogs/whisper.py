import logging

import discord
from discord.ext import commands

from scripts.modules.rsa import decrypt_message, encrypt_message

logger = logging.getLogger(__name__)


class DecryptButton(discord.ui.View):
    def __init__(self, encrypted_message: str, recipient_id: int):
        super().__init__(timeout=180)
        self.encrypted_message = encrypted_message
        self.recipient_id = recipient_id

    @discord.ui.button(label="Descifrar Mensaje", style=discord.ButtonStyle.primary)
    async def decrypt_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if interaction.user.id != self.recipient_id:
            await interaction.response.send_message(
                "No tienes permiso para descifrar este mensaje.", ephemeral=True
            )
            return

        try:
            decrypted_text: str = decrypt_message(
                self.encrypted_message, self.recipient_id
            )
            await interaction.response.send_message(
                f"**Mensaje secreto:**\n{decrypted_text}", ephemeral=True
            )
            button.disabled = True
            await interaction.edit_original_response(view=self)
        except Exception:
            await interaction.response.send_message(
                "Error al descifrar el mensaje. Puede que la clave sea incorrecta o el mensaje este dañado.",
                ephemeral=True,
            )


class Whisper(commands.Cog):
    def __init__(self, client, bd):
        self.client = client
        self.bd = bd

    def _is_protected(self, roles, protected_role_id: int) -> bool:
        return any(role.id == protected_role_id for role in roles)

    @commands.slash_command(
        name="whisper",
        description="Mensaje secreto a usuario. Si protegido envia/recibe whisper, se intercepta.",
    )
    async def whisper(
        self,
        ctx: discord.ApplicationContext,
        destinatario: discord.Option(
            discord.SlashCommandOptionType.user, "El usuario que podra leer el mensaje."
        ),
        mensaje: discord.Option(str, "El mensaje secreto que quieres enviar."),
    ) -> None:
        if destinatario is None:
            destinatario = ctx.author

        protected_role_id = self.bd[1]
        involves_protected = protected_role_id and (
            self._is_protected(ctx.author.roles, protected_role_id)
            or self._is_protected(destinatario.roles, protected_role_id)
        )

        embed = discord.Embed(
            title="Mensaje secreto",
            description=f"**Remitente:** {ctx.author.mention}\nPulsa el boton para leerlo. Expira en 3 minutos.",
            color=discord.Color.blue(),
        )

        try:
            encrypted_msg: str = encrypt_message(mensaje, destinatario.id)
            view = DecryptButton(encrypted_msg, destinatario.id)
            await destinatario.send(embed=embed, view=view)
        except discord.Forbidden:
            await ctx.respond(
                f"No puedo enviar mensajes directos a {destinatario.mention}. Asegurate de que sus DMs esten abiertos.",
                ephemeral=True,
            )
            return
        except Exception as e:
            logger.exception(f"Error enviando whisper a {destinatario.id}: {e}")
            await ctx.respond(
                "Ocurrio un error al enviar el mensaje secreto.",
                ephemeral=True,
            )
            return

        if involves_protected:
            await self.client._send_alert(
                ctx.author.mention,
                "",
                "Mensaje secreto",
                f"**Destinatario:** {destinatario.mention}\n```{mensaje}```",
            )

        await ctx.respond(
            f"Mensaje secreto enviado a {destinatario.mention}.", ephemeral=True
        )
