import os
import sys

import discord
from discord import default_permissions
from discord.ext import commands

from scripts.modules.database import insertRow


class SetData(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(name="set-data", description="")
    @default_permissions(administrator=True)
    async def set_data(
        self,
        ctx: discord.ApplicationContext,
        staff_channel: discord.TextChannel,
        role_protect: discord.Role,
    ):
        insertRow(staff_channel.id, role_protect.id)
        await ctx.respond("✅ Datos guardados correctamente.")
        os.execv(sys.executable, ["python"] + sys.argv)
