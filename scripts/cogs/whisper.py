import logging

import discord
from discord.ext import commands

from ..modules.rsa import decrypt_message, encrypt_message

logger = logging.getLogger(__name__)

_MAX_WHISPER_LENGTH = 2000


class DecryptButton(discord.ui.View):
    def __init__(
        self,
        encrypted_message: str,
        recipient_id: int,
        client=None,
        intercepted: bool = False,
        sender_mention: str = "",
    ):
        super().__init__(timeout=180)
        self.encrypted_message = encrypted_message
        self.recipient_id = recipient_id
        self.client = client
        self.intercepted = intercepted
        self.sender_mention = sender_mention
        self._unlocked = False

    @discord.ui.button(label="Descifrar Mensaje", style=discord.ButtonStyle.primary)
    async def decrypt_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if self._unlocked:
            await interaction.response.send_message(
                "Este mensaje ya fue descifrado.", ephemeral=True
            )
            return

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
            self._unlocked = True
            button.disabled = True
            # Editar el mensaje DM que contiene el boton (no la respuesta
            # efimera de esta interaccion) para que quede deshabilitado.
            try:
                if interaction.message:
                    await interaction.message.edit(view=self)
            except Exception:
                logger.debug(
                    "No se pudo desactivar el boton del whisper", exc_info=True
                )

            # Si el whisper involucra a un protegido, avisar al staff de que
            # el destinatario lo descifro (lectura confirmada).
            if self.intercepted and self.client is not None:
                try:
                    await self.client._send_alert(
                        interaction.user.mention,
                        "",
                        "​Mensaje secreto descifrado",
                        f"**Remitente:** {self.sender_mention}\n"
                        f"**Contenido:**\n```{decrypted_text[:950]}```",
                    )
                except Exception:
                    logger.exception("No se pudo notificar el descifrado al staff")
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
            discord.SlashCommandOptionType.user,
            description="El usuario que podra leer el mensaje.",
        ) = None,
        mensaje: discord.Option(
            str,
            description="El mensaje secreto que quieres enviar.",
        ) = "",
    ) -> None:
        if not mensaje:
            await ctx.respond("El mensaje no puede estar vacio.", ephemeral=True)
            return

        if len(mensaje) > _MAX_WHISPER_LENGTH:
            await ctx.respond(
                f"El mensaje es demasiado largo. Maximo {_MAX_WHISPER_LENGTH} caracteres.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

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
            view = DecryptButton(
                encrypted_msg,
                destinatario.id,
                client=self.client,
                intercepted=bool(involves_protected),
                sender_mention=ctx.author.mention,
            )
            await destinatario.send(embed=embed, view=view)
        except discord.Forbidden:
            await ctx.edit(
                content=f"No puedo enviar mensajes directos a {destinatario.mention}. Asegurate de que sus DMs esten abiertos."
            )
            return
        except Exception as e:
            logger.exception(f"Error enviando whisper a {destinatario.id}: {e}")
            await ctx.edit(
                content="Ocurrio un error al enviar el mensaje secreto."
            )
            return

        if involves_protected:
            await self.client._send_alert(
                ctx.author.mention,
                "",
                "\u200bMensaje secreto",
                f"**Destinatario:** {destinatario.mention}\n```{mensaje}```",
            )

        await ctx.edit(
            content=f"Mensaje secreto enviado a {destinatario.mention}."
        )
