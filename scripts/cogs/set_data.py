import discord
from discord import default_permissions
from discord.ext import commands

from scripts.modules.database import insert_row


class SetData(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        name="set-data",
        description="Guarda el canal de staff y el rol de proteccion en la base de datos.",
    )
    @default_permissions(administrator=True)
    async def set_data(
        self,
        ctx: discord.ApplicationContext,
        staff_channel: discord.TextChannel,
        role_protect: discord.Role,
    ):
        insert_row(staff_channel.id, role_protect.id)
        self.client.reload_data()
        await ctx.respond(
            "✅ Datos guardados y aplicados correctamente. No fue necesario reiniciar."
        )

    @commands.slash_command(
        name="reload-config",
        description="Recarga la configuracion desde bot_config.json sin reiniciar.",
    )
    @default_permissions(administrator=True)
    async def reload_config(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        success = await self.client.reload_config()
        if success:
            await ctx.respond("✅ Configuracion recargada correctamente.")
        else:
            await ctx.respond("⚠️ No se pudo leer bot_config.json. Revisa el archivo.")
