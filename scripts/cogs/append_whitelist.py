import asyncio
import json
import re
from pathlib import Path

import discord
from discord import default_permissions
from discord.ext import commands


class AppendWhitelistDomain(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.json_path = Path(__file__).parent.parent / "whitelist.json"

    @commands.slash_command(
        name="append-whitelist",
        description="Agrega un dominio a la lista blanca (no será analizado).",
    )
    @default_permissions(administrator=True)
    async def add_whitelist_domain(
        self,
        ctx: discord.ApplicationContext,  # ✅ Cambiado a ApplicationContext
        domain: discord.Option(str, "Dominio a agregar (ej: example.com)"),
    ) -> None:
        # Normalizar y validar
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
            # Si no existe, devuelve una lista vacía
            return []
        except json.JSONDecodeError:
            # Respalda el archivo corrupto y devuelve base
            backup_path = self.json_path.with_suffix(".json.bak")
            await asyncio.to_thread(self.json_path.rename, backup_path)
            return []

    async def _write_json(self, data: list) -> None:
        """Escribe el archivo JSON de forma no bloqueante."""
        content = json.dumps(data, indent=4, ensure_ascii=False)
        await asyncio.to_thread(self.json_path.write_text, content, encoding="utf-8")
