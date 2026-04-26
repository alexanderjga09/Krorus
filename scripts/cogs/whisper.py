import discord
from discord.ext import commands

from scripts.modules.fernet import decrypt_message, encrypt_message


class DecryptButton(discord.ui.View):
    def __init__(self, encrypted_message: str, recipient_id: int):
        super().__init__(timeout=180)
        self.encrypted_message = encrypted_message
        self.recipient_id = recipient_id

    @discord.ui.button(label="🔓 Descifrar Mensaje", style=discord.ButtonStyle.primary)
    async def decrypt_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if interaction.user.id != self.recipient_id:
            await interaction.response.send_message(
                "❌ No tienes permiso para descifrar este mensaje.", ephemeral=True
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
                "❌ Error al descifrar el mensaje. Puede que la clave sea incorrecta o el mensaje esté dañado.",
                ephemeral=True,
            )


class Whisper(commands.Cog):
    def __init__(self, client, bd):
        self.client = client
        self.bd = bd

    @commands.slash_command(
        name="whisper",
        description="Mensaje secreto a usuario. Si protegido envía/recibe whisper, se intercepta.",
    )
    async def whisper(
        self,
        ctx: discord.ApplicationContext,
        destinatario: discord.Option(
            discord.SlashCommandOptionType.user, "El usuario que podrá leer el mensaje."
        ),
        mensaje: discord.Option(str, "El mensaje secreto que quieres enviar."),
    ) -> None:
        if destinatario is None:
            destinatario = ctx.author

        encrypted_msg: str = encrypt_message(mensaje, destinatario.id)
        view = DecryptButton(encrypted_msg, destinatario.id)

        protected_role_id = self.bd[1]
        if protected_role_id and (
            any(role.id == protected_role_id for role in ctx.author.roles)
            or any(role.id == protected_role_id for role in destinatario.roles)
        ):
            await self.client._send_alert(
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
