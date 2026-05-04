import discord
from discord.ext import commands


class HealthCheck(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        name="ping", description="Verifica que el bot esta funcionando."
    )
    async def ping(self, ctx: discord.ApplicationContext):
        await ctx.respond(f"🏓 Pong! Latencia: {round(self.client.latency * 1000)}ms")

    @commands.slash_command(name="status", description="Muestra el estado del bot.")
    async def status(self, ctx: discord.ApplicationContext):
        rate_limited = self.client._rate_limit_until > 0
        rss = "🔴 Rate Limited" if rate_limited else "🟢 Normal"

        embed = discord.Embed(
            title="Estado del Bot",
            description=f"- **Rate Limit:** {rss}\n- **Latencia:** {round(self.client.latency * 1000)}ms",
            color=discord.Color.blue(),
        )

        await ctx.respond(embed=embed)
