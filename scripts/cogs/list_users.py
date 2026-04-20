import discord
from discord import default_permissions
from discord.ext import commands

from scripts.modules.logs import Logs


class ListUsers(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(name="list-users", description="")
    @default_permissions(administrator=True)
    async def list_users(self, ctx: discord.ApplicationContext) -> None:
        logs = Logs()
        users = logs.listUsers()

        list = []

        for user, alerts in users:
            list.append((user, len(alerts)))

        embed = discord.Embed(
            title="Usuarios con alertas",
            description="\n".join(
                [
                    f"<@{user}>: {alerts} alertas"
                    for user, alerts in sorted(list, key=lambda x: x[1], reverse=True)
                ]
            ),
            color=discord.Color.blue(),
        )

        await ctx.respond(embed=embed)
