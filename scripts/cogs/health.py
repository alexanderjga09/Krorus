import time
import sys
import discord
from discord.ext import commands


class HealthCheck(commands.Cog):
    def __init__(self, client):
        self.client = client
        self._start_time = time.time()

    def _get_uptime(self) -> str:
        seconds = int(time.time() - self._start_time)
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)

    @commands.slash_command(
        name="ping", description="Verifica que el bot esta funcionando."
    )
    async def ping(self, ctx: discord.ApplicationContext):
        await ctx.respond(f"🏓 Pong! Latencia: {round(self.client.latency * 1000)}ms")

    @commands.slash_command(name="status", description="Muestra el estado del bot.")
    async def status(self, ctx: discord.ApplicationContext):
        rate_limited = self.client.is_rate_limited()
        guild = ctx.guild
        total_members = guild.member_count if guild else 0

        embed = discord.Embed(
            title="🤖 Estado del Bot",
            color=discord.Color.orange() if rate_limited else discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="⏱️ Tiempo activo", value=self._get_uptime(), inline=True
        )
        embed.add_field(
            name="📶 Latencia",
            value=f"{round(self.client.latency * 1000)}ms",
            inline=True,
        )
        embed.add_field(name="🚦 Rate Limit", value="🟢 Normal" if not rate_limited else "🔴 Rate Limited", inline=True)
        embed.add_field(
            name="👥 Usuarios", value=str(total_members), inline=True
        )
        embed.add_field(
            name="🐍 Python",
            value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            inline=True,
        )
        embed.add_field(name="📦 py-cord", value=discord.__version__, inline=True)
        embed.add_field(
            name="📂 Cogs activos", value=str(len(self.client.cogs)), inline=True
        )
        embed.add_field(
            name="🆔 Bot ID",
            value=f"`{self.client.user.id}`" if self.client.user else "N/A",
            inline=True,
        )

        await ctx.respond(embed=embed)
