import discord
from discord import default_permissions
from discord.ext import commands

from scripts.modules.logs import Logs


class CheckUser(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(name="check-user", description="")
    @default_permissions(administrator=True)
    async def check(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, "El usuario a chequear"),
    ) -> None:
        logs = Logs()
        users = logs.listUsers()

        for user in users:
            if user[0] == str(member.id):
                user_alerts = user[1]
                break
        else:
            await ctx.respond(f"No hay alertas para {member.display_name}")
            return

        alert_list: str = "\n".join(
            [
                f"`{alert['code']}` {alert['alert']} | :mailbox_with_mail: [Ir al mensaje]({alert['url']})"
                for alert in user_alerts
            ]
        )

        embed = discord.Embed(
            title=f"Alertas de {member.display_name}",
            description=alert_list or "No hay alertas",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=member.avatar.url)

        await ctx.respond(embed=embed)
