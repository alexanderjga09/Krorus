"""Paginador reutilizable para embeds de Discord (py-cord)."""

from __future__ import annotations

import discord


class Paginator(discord.ui.View):
    def __init__(
        self,
        pages: list[discord.Embed],
        author_id: int,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        if not pages:
            raise ValueError("Paginator requiere al menos una página.")
        self.pages = pages
        self.author_id = author_id
        self.current = 0
        self.message: discord.Message | None = None
        self._sync_buttons()

    # ── Internals ─────────────────────────────────────────────────────────

    def _sync_buttons(self) -> None:
        """Actualiza el estado disabled de los botones según la página actual."""
        self.btn_prev.disabled = self.current == 0
        self.btn_next.disabled = self.current >= len(self.pages) - 1

    async def _guard(self, interaction: discord.Interaction) -> bool:
        """Rechaza interacciones de usuarios distintos al autor del comando."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Solo quien ejecutó el comando puede navegar por estas páginas.",
                ephemeral=True,
            )
            return False
        return True

    # ── Botones ───────────────────────────────────────────────────────────

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.secondary)
    async def btn_prev(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if not await self._guard(interaction):
            return
        self.current -= 1
        self._sync_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current], view=self
        )

    @discord.ui.button(emoji="❌", style=discord.ButtonStyle.primary)
    async def btn_close(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if not await self._guard(interaction):
            return
        await interaction.message.delete()
        self.stop()

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.secondary)
    async def btn_next(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if not await self._guard(interaction):
            return
        self.current += 1
        self._sync_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current], view=self
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def on_timeout(self) -> None:
        """Desactiva todos los botones cuando caduca la sesión de interacción."""
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
        self.stop()
