from datetime import datetime

import discord
from discord import default_permissions
from discord.ext import commands

from ..modules.chainlog import get_chain_log
from ..modules.pagination import Paginator

# Número de alertas por página del paginador
_ALERTS_PER_PAGE = 5


def _build_pages(
    member: discord.Member,
    alerts: list,
    chain_log,
) -> list[discord.Embed]:
    """Convierte la lista de alertas en páginas de embed listas para el Paginator."""
    total = len(alerts)
    chunks = [
        alerts[i : i + _ALERTS_PER_PAGE] for i in range(0, total, _ALERTS_PER_PAGE)
    ]
    pages: list[discord.Embed] = []

    for i, chunk in enumerate(chunks):
        lines: list[str] = []
        for alert in chunk:
            code = alert["data"]["code"]
            ts = datetime.fromisoformat(alert["timestamp"])
            hora = ts.strftime("%H:%M:%S")
            fecha = ts.strftime("%d-%m-%Y")
            reason = alert["data"]["reason"]
            url = alert["data"]["jump_url"]
            pardoned = chain_log.is_pardoned(alert["index"])
            estado = "⚪ Perdonada | " if pardoned else ""
            lines.append(
                f"`{code}` ({hora} | {fecha})\n"
                f"{estado}{reason} [:mailbox_with_mail:]({url})\n_ _"
            )

        embed = discord.Embed(
            title=f"Alertas de {member.display_name}",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(
            text=f"Página {i + 1} / {len(chunks)}  ·  {total} alerta(s) en total"
        )
        pages.append(embed)

    return pages


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
        chain_log = get_chain_log()
        alerts = chain_log.get_user_alerts(str(member.id), include_pardoned=True)

        if not alerts:
            await ctx.respond(
                f"✅ **{member.display_name}** no tiene ninguna alerta registrada.",
                ephemeral=True,
            )
            return

        pages = _build_pages(member, alerts, chain_log)

        if len(pages) == 1:
            # Una sola página: no hacen falta botones de navegación
            await ctx.respond(embed=pages[0])
            return

        view = Paginator(pages, author_id=ctx.author.id)
        await ctx.respond(embed=pages[0], view=view)
        # Guardamos la referencia al mensaje para que on_timeout pueda desactivar los botones
        view.message = await ctx.interaction.original_response()

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
        chain_log = get_chain_log()
        block_index = chain_log.find_alert_index_by_code(code)

        if block_index is None:
            await ctx.respond(
                f"No se encontró una alerta activa con el código `{code}`.",
                ephemeral=True,
            )
            return

        if chain_log.is_pardoned(block_index):
            await ctx.respond("Esa alerta ya fue perdonada.", ephemeral=True)
            return

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
