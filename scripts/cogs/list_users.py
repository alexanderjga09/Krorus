import discord
from discord import default_permissions
from discord.ext import commands

from ..modules.chainlog import get_chain_log
from ..modules.pagination import Paginator

# Número de usuarios por página del paginador
_USERS_PER_PAGE = 10


def _build_pages(sorted_users: list) -> list[discord.Embed]:
    """Divide la lista de usuarios con alertas en páginas de embed."""
    total = len(sorted_users)
    chunks = [
        sorted_users[i : i + _USERS_PER_PAGE] for i in range(0, total, _USERS_PER_PAGE)
    ]
    pages: list[discord.Embed] = []

    for i, chunk in enumerate(chunks):
        lines = [f"<@{uid}> — **{count}** alerta(s)" for uid, count in chunk]
        embed = discord.Embed(
            title="👥 Usuarios con alertas activas",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Página {i + 1} / {len(chunks)}  ·  {total} usuario(s)")
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
        users = chain_log.list_users()

        if not users:
            await ctx.respond("✅ No hay usuarios con alertas activas.", ephemeral=True)
            return

        sorted_users = sorted(users, key=lambda x: x[1], reverse=True)
        pages = _build_pages(sorted_users)

        if len(pages) == 1:
            # Una sola página: no hacen falta botones de navegación
            await ctx.respond(embed=pages[0])
            return

        view = Paginator(pages, author_id=ctx.author.id)
        await ctx.respond(embed=pages[0], view=view)
        # Guardamos la referencia al mensaje para que on_timeout pueda desactivar los botones
        view.message = await ctx.interaction.original_response()

    @commands.slash_command(
        name="verify-chain", description="Verificar integridad de la cadena de alertas"
    )
    @default_permissions(administrator=True)
    async def verify_chain(self, ctx: discord.ApplicationContext):
        chain_log = get_chain_log()
        valid = chain_log.verify_chain()
        await ctx.respond(
            f"¿Cadena íntegra? {'✅ Sí' if valid else '❌ NO, manipulación detectada'}"
        )
