import asyncio
import json
import re
from pathlib import Path

import discord
from discord import default_permissions
from discord.ext import commands

from ..modules.pagination import Paginator

_DOMAINS_PER_PAGE = 15


def _build_pages(domains: list[str]) -> list[discord.Embed]:
    """Divide la lista de dominios en páginas de embed listas para el Paginator."""
    total = len(domains)
    chunks = [
        domains[i : i + _DOMAINS_PER_PAGE] for i in range(0, total, _DOMAINS_PER_PAGE)
    ]
    pages: list[discord.Embed] = []

    for i, chunk in enumerate(chunks):
        offset = i * _DOMAINS_PER_PAGE
        lines = [f"`{offset + j + 1}.` {domain}" for j, domain in enumerate(chunk)]
        embed = discord.Embed(
            title="✅ Lista blanca de dominios",
            description="\n".join(lines),
            color=discord.Color.green(),
        )
        embed.set_footer(
            text=f"Página {i + 1} / {len(chunks)}  ·  {total} dominio(s) en total"
        )
        pages.append(embed)

    return pages


class AppendWhitelistDomain(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.json_path = Path(__file__).parent.parent.parent / "data" / "whitelist.json"

    @commands.slash_command(
        name="append-whitelist",
        description="Agrega un dominio a la lista blanca (no será analizado).",
    )
    @default_permissions(administrator=True)
    async def add_whitelist_domain(
        self,
        ctx: discord.ApplicationContext,
        domain: discord.Option(str, "Dominio a agregar (ej: example.com)"),
    ) -> None:
        domain = domain.strip().lower()
        if not self._is_valid_domain(domain):
            await ctx.respond("❌ El formato del dominio no es válido.", ephemeral=True)
            return

        async with self.lock:
            data = await self._read_json()

            if domain in data:
                await ctx.respond(
                    f"⚠️ El dominio **{domain}** ya está en la lista blanca.",
                    ephemeral=True,
                )
                return

            data.append(domain)
            await self._write_json(data)

        await ctx.respond(f"✅ Dominio **{domain}** agregado a la lista blanca.")

    @commands.slash_command(
        name="remove-whitelist-domain",
        description="Remover un dominio de la whitelist.",
    )
    @default_permissions(administrator=True)
    async def remove_whitelist_domain(
        self,
        ctx: discord.ApplicationContext,
        domain: discord.Option(str, "Dominio a remover (ej: example.com)"),
    ) -> None:
        domain = domain.strip().lower()
        if not self._is_valid_domain(domain):
            await ctx.respond(
                f"❌ El dominio **{domain}** no es válido.", ephemeral=True
            )
            return

        async with self.lock:
            data = await self._read_json()
            if domain not in data:
                await ctx.respond(
                    f"❌ Dominio **{domain}** no está en la lista.", ephemeral=True
                )
                return
            data.remove(domain)
            await self._write_json(data)

        await ctx.respond(f"✅ Dominio **{domain}** eliminado de la lista blanca.")

    @commands.slash_command(
        name="view-whitelist",
        description="Muestra los dominios configurados en la lista blanca.",
    )
    @default_permissions(administrator=True)
    async def view_whitelist(self, ctx: discord.ApplicationContext) -> None:
        async with self.lock:
            data = await self._read_json()

        if not data:
            await ctx.respond("⚠️ No hay dominios en la lista blanca.", ephemeral=True)
            return

        pages = _build_pages(sorted(data))

        if len(pages) == 1:
            await ctx.respond(embed=pages[0], ephemeral=True)
            return

        view = Paginator(pages, author_id=ctx.author.id)
        await ctx.respond(embed=pages[0], view=view, ephemeral=True)
        view.message = await ctx.interaction.original_response()

    def _is_valid_domain(self, domain: str) -> bool:
        pattern = r"^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$"
        return re.match(pattern, domain) is not None

    async def _read_json(self) -> list:
        """Lee el archivo JSON de forma no bloqueante."""
        try:
            content = await asyncio.to_thread(
                self.json_path.read_text, encoding="utf-8"
            )
            return json.loads(content)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            backup_path = self.json_path.with_suffix(".json.bak")
            await asyncio.to_thread(self.json_path.rename, backup_path)
            return []

    async def _write_json(self, data: list) -> None:
        """Escribe el archivo JSON de forma no bloqueante."""
        content = json.dumps(data, indent=4, ensure_ascii=False)
        await asyncio.to_thread(self.json_path.write_text, content, encoding="utf-8")
