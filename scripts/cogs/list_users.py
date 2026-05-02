from datetime import datetime

import discord
from discord import default_permissions
from discord.ext import commands

from ..modules.chainlog import get_chain_log
from ..modules.pagination import Paginator

_USERS_PER_PAGE = 6

_RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}


def _enrich_users(chain_log, alerts_by_user: dict) -> list:
    result = []
    for uid, alerts in alerts_by_user.items():
        if not alerts:
            continue

        active = sum(1 for a in alerts if not chain_log.is_pardoned(a["index"]))
        if active == 0:
            continue

        pardoned = len(alerts) - active
        latest = max(alerts, key=lambda a: a["timestamp"])
        result.append(
            (
                uid,
                active,
                pardoned,
                latest["timestamp"],
                latest["data"]["reason"],
                latest["data"]["jump_url"],
            )
        )

    return sorted(result, key=lambda x: x[1], reverse=True)


def _build_pages(enriched: list) -> list[discord.Embed]:
    """Divide la lista enriquecida en páginas de embed con campos por usuario."""
    total_users = len(enriched)
    total_active = sum(e[1] for e in enriched)
    chunks = [
        enriched[i : i + _USERS_PER_PAGE]
        for i in range(0, total_users, _USERS_PER_PAGE)
    ]
    pages: list[discord.Embed] = []

    for page_i, chunk in enumerate(chunks):
        embed = discord.Embed(
            title="🚨 Usuarios con conducta irregular",
            description=(
                f"**{total_active}** alerta(s) activa(s) "
                f"en **{total_users}** usuario(s) registrado(s)"
            ),
            color=discord.Color.orange(),
        )

        for entry_i, (
            uid,
            active,
            pardoned,
            last_ts,
            last_reason,
            jump_url,
        ) in enumerate(chunk):
            rank = page_i * _USERS_PER_PAGE + entry_i + 1
            rank_str = _RANK_EMOJI.get(rank, f"`#{rank}`")

            ts = datetime.fromisoformat(last_ts)
            fecha_hora = ts.strftime("%d/%m/%Y · %H:%M")

            reason_short = (
                (last_reason[:65] + "…") if len(last_reason) > 65 else last_reason
            )
            pardoned_text = (
                f"  ·  ⚪ **{pardoned}** perdonada(s)" if pardoned > 0 else ""
            )

            embed.add_field(
                name=rank_str,
                value=(
                    f"<@{uid}>  🔴 **{active}** activa(s){pardoned_text}\n"
                    f"📅 {fecha_hora}  —  {reason_short} [:mailbox_with_mail:]({jump_url})"
                ),
                inline=False,
            )

        embed.set_footer(
            text=f"Página {page_i + 1} / {len(chunks)}  ·  {total_users} usuario(s) sancionado(s)"
        )
        pages.append(embed)

    return pages


class ListUsers(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        name="list-users", description="Listar usuarios con alertas activas"
    )
    @default_permissions(administrator=True)
    async def list_users(self, ctx: discord.ApplicationContext) -> None:
        chain_log = get_chain_log()
        alerts_by_user = chain_log.get_alerts_by_user(include_pardoned=True)

        if not alerts_by_user:
            await ctx.respond("✅ No hay usuarios con alertas activas.", ephemeral=True)
            return

        enriched = _enrich_users(chain_log, alerts_by_user)

        if not enriched:
            await ctx.respond("✅ No hay usuarios con alertas activas.", ephemeral=True)
            return

        pages = _build_pages(enriched)

        if len(pages) == 1:
            await ctx.respond(embed=pages[0])
            return

        view = Paginator(pages, author_id=ctx.author.id)
        await ctx.respond(embed=pages[0], view=view)
        view.message = await ctx.interaction.original_response()

    @commands.slash_command(
        name="verify-chain", description="Verificar integridad de la cadena de alertas"
    )
    async def verify_chain(self, ctx: discord.ApplicationContext):
        chain_log = get_chain_log()
        valid = chain_log.verify_chain()
        await ctx.respond(
            f"¿Cadena íntegra? {'✅ Sí' if valid else '❌ NO, manipulación detectada'}"
        )
