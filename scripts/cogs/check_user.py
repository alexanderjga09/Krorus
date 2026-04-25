from datetime import datetime
from pathlib import Path

import discord
from discord import default_permissions
from discord.ext import commands

from scripts.modules.chainlog import ChainLog


class CheckUser(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        name="check-user", description="Consultar alertas de un usuario"
    )
    @default_permissions(administrator=True)
    async def check(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, "El usuario a chequear"),
    ) -> None:
        # Obtener las alertas del usuario (incluyendo las perdonadas para historia completa)
        chain_log = ChainLog(
            str(Path(__file__).parent.parent.parent / "data" / "logs.json")
        )
        alerts = chain_log.get_user_alerts(str(member.id), include_pardoned=True)

        if not alerts:
            await ctx.respond(f"No hay alertas para {member.display_name}")
            return

        # Formatear cada alerta como en tu captura
        alert_list_lines = []
        for alert in alerts:
            code = alert["data"]["code"]
            # Convertir timestamp ISO a formato "HH:MM:SS | DD-MM-YYYY"
            ts = datetime.fromisoformat(alert["timestamp"])
            hora = ts.strftime("%H:%M:%S")
            fecha = ts.strftime("%d-%m-%Y")
            reason = alert["data"]["reason"]
            url = alert["data"]["jump_url"]
            # Marcar si está perdonada (opcional, puedes quitarlo si no quieres mostrarlo)
            pardoned = chain_log.is_pardoned(alert["index"])
            estado = "⚪ Perdonada | " if pardoned else ""
            # Construir línea exactamente como antes
            linea = f"`{code}` ({hora} | {fecha})\n{estado}{reason} [:mailbox_with_mail:]({url})\n_ _"
            alert_list_lines.append(linea)

        embed = discord.Embed(
            title=f"Alertas de {member.display_name}",
            description="\n".join(alert_list_lines) or "No hay alertas",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=member.avatar.url)

        await ctx.respond(embed=embed)

    @commands.slash_command(
        name="pardon",
        description="Perdonar una alerta por su código (añade bloque de anulación)",
    )
    @default_permissions(administrator=True)
    @discord.option(
        "code", str, description="Código de la alerta a perdonar (ej. D21B1DC6ee)"
    )
    @discord.option("reason", str, description="Motivo del perdón")
    async def pardon(self, ctx: discord.ApplicationContext, code: str, reason: str):
        # Usa la instancia global de chain_log (asegúrate de que esté importada)
        chain_log = ChainLog(
            str(Path(__file__).parent.parent.parent / "data" / "logs.json")
        )
        block_index = chain_log.find_alert_index_by_code(code)
        if block_index is None:
            await ctx.respond(
                f"No se encontró una alerta activa con el código `{code}`.",
                ephemeral=True,
            )
            return

        # Verificar que no esté ya perdonada (redundante porque find_alert_index_by_code con only_active=True ya lo filtra)
        if chain_log.is_pardoned(block_index):
            await ctx.respond("Esa alerta ya fue perdonada.", ephemeral=True)
            return

        # Añadir bloque de perdón
        result = chain_log.add_pardon(
            original_block_index=block_index,
            moderator_id=str(ctx.author.id),
            reason=reason,
        )
        if result:
            await ctx.respond(
                f"✅ Alerta `{code}` perdonada. Hash del bloque de perdón: `{result[:8]}...`"
            )
        else:
            await ctx.respond("No se pudo añadir el perdón.", ephemeral=True)
