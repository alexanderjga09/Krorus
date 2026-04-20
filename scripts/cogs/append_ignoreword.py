import asyncio
import json
import re
from pathlib import Path

from discord import default_permissions
from discord.ext import commands


class AppendIgnoreWord(commands.Cog):
    def __init__(self, bot, path: Path):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.json_path = path
        self.ignore_words = []  # Lista original
        self.ignore_words_set = set()  # Para comparación exacta (O(1))
        self.ignore_pattern = None  # Expresión regular compilada

    async def cog_load(self):
        """Carga inicial de datos y compilación del patrón."""
        data = await self._read_json()
        self.ignore_words = data
        self._rebuild_matchers()

    def _rebuild_matchers(self):
        self.ignore_words_set = {w.lower() for w in self.ignore_words}

        if self.ignore_words:
            escaped = [re.escape(w) for w in self.ignore_words]
            pattern = rf"^\s*({'|'.join(escaped)})(?:\s|$)"
            self.ignore_pattern = re.compile(pattern, re.IGNORECASE)
        else:
            self.ignore_pattern = None

    @commands.slash_command(
        name="append-ignoreword",
        description="Append a word to the ignoreword list",
    )
    @default_permissions(administrator=True)
    async def append_ignoreword(self, ctx, words: str):
        new_words = [w.strip() for w in words.split(",") if w.strip()]
        async with self.lock:
            self.ignore_words.extend(new_words)
            await self._write_json(self.ignore_words)
            self._rebuild_matchers()
        await ctx.respond(f"Se añadieron {len(new_words)} palabras a la lista.")

    @commands.slash_command(
        name="reload-ignorewords", description="Reload the ignoreword list"
    )
    @default_permissions(administrator=True)
    async def reload_ignorewords(self, ctx):
        async with self.lock:
            self.ignore_words = await self._read_json()
            self._rebuild_matchers()
        await ctx.respond("Lista de palabras ignoradas recargada.", ephemeral=True)

    async def _read_json(self) -> list:
        try:
            content = await asyncio.to_thread(
                self.json_path.read_text, encoding="utf-8"
            )
            return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    async def _write_json(self, data: list) -> None:
        content = json.dumps(data, indent=4, ensure_ascii=False)
        await asyncio.to_thread(self.json_path.write_text, content, encoding="utf-8")

    def should_ignore(self, content: str) -> bool:
        if not self.ignore_pattern:
            return False
        return bool(self.ignore_pattern.match(content))
