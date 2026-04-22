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
        self._load_data()

    def _load_data(self):
        """Carga los datos del JSON y reconstruye los matchers."""
        try:
            content = self.json_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"⚠️ No se pudo cargar {self.json_path}: {e}")
            data = []
        self.ignore_words = data
        self._rebuild_matchers()
        print(f"✅ AppendIgnoreWord cargado con {len(self.ignore_words)} palabras.")

    async def cog_load(self):
        """Carga inicial de datos y compilación del patrón."""
        data = await self._read_json()
        self.ignore_words = data
        self._rebuild_matchers()

    def _rebuild_matchers(self):
        """Construye el set de búsqueda rápida y el patrón regex restrictivo."""
        self.ignore_words_set = {w.lower() for w in self.ignore_words}

        if self.ignore_words:
            # Escapamos cada palabra comando
            escaped_commands = [re.escape(w) for w in self.ignore_words]
            commands_pattern = "|".join(escaped_commands)

            # Patrón para argumentos válidos de Mudae:
            # - números (opcionalmente con 'k')
            # - flags como -s, -c (letras minúsculas)
            # - menciones <@!?123456>
            valid_arg = r"(?:\s+(?:-?[a-z]+|\d+k?|<@!?\d+>))*"

            # El mensaje completo debe ser: inicio, comando, argumentos válidos, fin
            pattern = rf"^\s*({commands_pattern}){valid_arg}\s*$"
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
        name="remove-ignoreword",
        description="Remove a word from the ignoreword list",
    )
    @default_permissions(administrator=True)
    async def remove_ignoreword(self, ctx, word: str):
        word = word.strip().lower()
        async with self.lock:
            if word in self.ignore_words:
                self.ignore_words.remove(word)
                await self._write_json(self.ignore_words)
                self._rebuild_matchers()
                await ctx.respond(f"✅ Palabra **{word}** eliminada de la lista.")
            else:
                await ctx.respond(
                    f"❌ Palabra **{word}** no está en la lista.", ephemeral=True
                )

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
