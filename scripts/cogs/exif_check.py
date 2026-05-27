import logging
from pathlib import Path

import discord
from discord import default_permissions
from discord.ext import commands

from ..modules.exif_checker import check_archive_exif

logger = logging.getLogger(__name__)


class ExifCheck(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        name="check-exif",
        description="Verifica metadatos EXIF sensibles en un archivo adjunto.",
    )
    @default_permissions(administrator=True)
    async def check_exif(
        self, ctx: discord.ApplicationContext, mensaje: str | None = None
    ):
        target_msg = None

        if mensaje:
            try:
                msg_id = int(mensaje)
                target_msg = await ctx.channel.fetch_message(msg_id)
            except (ValueError, discord.NotFound):
                await ctx.respond(
                    ":x: No se encontro el mensaje con esa ID.", ephemeral=True
                )
                return
        elif ctx.message.reference:
            try:
                target_msg = await ctx.channel.fetch_message(
                    ctx.message.reference.message_id
                )
            except discord.NotFound:
                await ctx.respond(
                    ":x: No se encontro el mensaje al que respondes.", ephemeral=True
                )
                return
        else:
            await ctx.respond(
                ":information_source: Responde a un mensaje con el archivo o usa `/check-exif mensaje: <ID>`.",
                ephemeral=True,
            )
            return

        if not target_msg or not target_msg.attachments:
            await ctx.respond(
                ":x: El mensaje no tiene archivos adjuntos.", ephemeral=True
            )
            return

        await ctx.response.defer(ephemeral=True)

        reports = []
        for att in target_msg.attachments:
            ext = Path(att.filename).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".zip"):
                continue

            try:
                file_data = await att.read()
                report = check_archive_exif(file_data, att.filename, att.content_type)
                if report.has_sensitive_data or report.files_checked > 0:
                    reports.append(report)
            except Exception as e:
                logger.error(f"[EXIF CMD] Error procesando {att.filename}: {e}")

        if not reports:
            await ctx.followup.send(
                ":white_check_mark: No se encontraron datos EXIF sensibles en los archivos.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔍 Reporte EXIF",
            color=0xFF6600 if any(r.has_high_risk for r in reports) else 0x0099FF,
        )

        for report in reports:
            risk = "🚨 ALTO RIESGO" if report.has_high_risk else "⚠️ Datos sensibles"
            safe = "✅ Seguro" if not report.has_sensitive_data else ""
            status = risk if risk else safe

            value = (
                f"**Estado:** {status}\n"
                f"**Archivos revisados:** {report.files_checked}\n"
                f"**Con EXIF:** {report.files_with_exif}\n"
            )

            if report.findings:
                value += "\n**Hallazgos:**\n"
                for f in report.findings[:10]:
                    icon = "🚨" if f.is_high_risk else "⚠️"
                    value += f"{icon} `{f.filename}` → {f.description}\n"
                if len(report.findings) > 10:
                    value += f"... y {len(report.findings) - 10} mas\n"

            embed.add_field(
                name=f"📦 {report.archive_filename}",
                value=value,
                inline=False,
            )

        await ctx.followup.send(embed=embed, ephemeral=True)
