from pathlib import Path

import discord
from discord import default_permissions
from discord.ext import commands

from chainlog_rs import ChainLog


class ListUsers(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        name="list-users", description="Listar usuarios con alertas activas"
    )
    @default_permissions(administrator=True)
    async def list_users(self, ctx: discord.ApplicationContext) -> None:
        chain_log = ChainLog(
            str(Path(__file__).parent.parent.parent / "data" / "logs.json")
        )
        users = chain_log.list_users()  # Devuelve [(user_id, num_alertas), ...]

        if not users:
            await ctx.respond("No hay usuarios con alertas activas.")
            return

        # Ordenar por número de alertas descendente
        sorted_users = sorted(users, key=lambda x: x[1], reverse=True)

        description = "\n".join(
            [f"<@{uid}> ({count} alertas)" for uid, count in sorted_users]
        )

        embed = discord.Embed(
            title="Usuarios con alertas activas",
            description=description,
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

    @commands.slash_command(
        name="verify_chain", description="Verificar integridad de la cadena de alertas"
    )
    @commands.is_owner()
    async def verify_chain(self, ctx: discord.ApplicationContext):
        chain_log = ChainLog(
            str(Path(__file__).parent.parent.parent / "data" / "logs.json")
        )
        valid = chain_log.verify_chain()
        await ctx.respond(
            f"¿Cadena íntegra? {'✅ Sí' if valid else '❌ NO, manipulación detectada'}"
        )
