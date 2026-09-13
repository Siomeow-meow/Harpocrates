# cogs/platform_setup.py
"""
Platform setup, now driven by a single slash command that opens an
interactive panel (dropdown + buttons + modal) instead of three separate
slash commands the user had to remember (setup_platform / list_platforms /
remove_platform).

Requires discord.py >= 2.3 (for discord.ui.Select in decorator form).
"""

import discord
from discord import app_commands
from discord.ext import commands

PLATFORM_OPTIONS = [
    discord.SelectOption(label="YouTube", value="youtube", emoji="🎥"),
    discord.SelectOption(label="Twitch", value="twitch", emoji="🟣"),
]

PLATFORM_ICON = {"youtube": "🎥", "twitch": "🟣"}


def get_platform_instance(bot, platform: str):
    if platform == "youtube":
        return bot.youtube_platform
    elif platform == "twitch":
        return bot.twitch_platform
    return None


async def build_platforms_embed(bot, guild_id: str) -> discord.Embed:
    """Same content /list_platforms used to show, reused by the panel + Refresh button."""
    configured = []

    if bot.youtube_platform and bot.youtube_platform.is_configured(guild_id):
        configured.append("🎥 YouTube")
    if bot.twitch_platform and bot.twitch_platform.is_configured(guild_id):
        configured.append("🟣 Twitch")

    embed = discord.Embed(title="🌐 Platform Manager", color=discord.Color.blue())

    if configured:
        embed.add_field(name=f"Active Platforms ({len(configured)})",
                         value="\n".join(configured), inline=False)
    else:
        embed.add_field(name="Active Platforms", value="*None configured yet*", inline=False)

    embed.description = "Pick a platform below, then **Setup**, **Remove**, or **Refresh**."
    return embed


class PlatformSetupModal(discord.ui.Modal, title="Platform Setup"):
    api_key = discord.ui.TextInput(
        label="API Key / Client ID",
        placeholder="YouTube API key, or Twitch Client ID",
        required=True,
        max_length=200,
    )
    secret_key = discord.ui.TextInput(
        label="Client Secret (Twitch only)",
        placeholder="Leave blank for YouTube",
        required=False,
        max_length=200,
    )

    def __init__(self, bot, platform: str, dashboard_message: discord.Message = None):
        super().__init__()
        self.bot = bot
        self.platform = platform
        self.dashboard_message = dashboard_message
        # Twitch needs the secret field; make that obvious without hard-blocking submit.
        if platform == "twitch":
            self.secret_key.label = "Client Secret (required for Twitch)"

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        platform_instance = get_platform_instance(self.bot, self.platform)
        if not platform_instance:
            await interaction.followup.send(f"❌ Platform **{self.platform}** is not available.", ephemeral=True)
            return

        if self.platform == "twitch" and not self.secret_key.value:
            await interaction.followup.send(
                "❌ Twitch requires both a Client ID and Client Secret. Please try Setup again.",
                ephemeral=True,
            )
            return

        if self.platform == "youtube":
            success = await platform_instance._setup_youtube(interaction, self.api_key.value)
        else:
            success = await platform_instance._setup_twitch(interaction, self.api_key.value, self.secret_key.value)

        if success:
            guild_id = str(interaction.guild.id)
            if not hasattr(self.bot, "configured_platforms"):
                self.bot.configured_platforms = {}
            self.bot.configured_platforms.setdefault(guild_id, [])
            if self.platform not in self.bot.configured_platforms[guild_id]:
                self.bot.configured_platforms[guild_id].append(self.platform)

            # Refresh the original panel embed in place, if we have it.
            if self.dashboard_message:
                try:
                    embed = await build_platforms_embed(self.bot, guild_id)
                    await self.dashboard_message.edit(embed=embed)
                except discord.HTTPException:
                    pass


class PlatformDashboard(discord.ui.View):
    def __init__(self, bot, guild_id: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_platform = None
        self.message: discord.Message = None  # set after sending, so buttons can refresh it

    @discord.ui.select(placeholder="Choose a platform...", options=PLATFORM_OPTIONS)
    async def platform_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_platform = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Setup", style=discord.ButtonStyle.green, emoji="⚙️")
    async def setup_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_platform:
            await interaction.response.send_message("Pick a platform from the dropdown first.", ephemeral=True)
            return
        await interaction.response.send_modal(
            PlatformSetupModal(self.bot, self.selected_platform, dashboard_message=self.message)
        )

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.red, emoji="🗑️")
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_platform:
            await interaction.response.send_message("Pick a platform from the dropdown first.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        platform_instance = get_platform_instance(self.bot, self.selected_platform)

        if not platform_instance:
            await interaction.followup.send(f"❌ Platform **{self.selected_platform}** is not available.", ephemeral=True)
            return

        if not platform_instance.is_configured(guild_id):
            await interaction.followup.send(
                f"❌ **{self.selected_platform.title()}** isn't configured for this server.", ephemeral=True
            )
            return

        success = platform_instance.remove_config(guild_id)
        if success:
            if hasattr(self.bot, "configured_platforms") and guild_id in self.bot.configured_platforms:
                if self.selected_platform in self.bot.configured_platforms[guild_id]:
                    self.bot.configured_platforms[guild_id].remove(self.selected_platform)

            embed = await build_platforms_embed(self.bot, guild_id)
            await interaction.message.edit(embed=embed)
            await interaction.followup.send(f"✅ Removed **{self.selected_platform.title()}** configuration.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to remove **{self.selected_platform.title()}** configuration.", ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await build_platforms_embed(self.bot, str(interaction.guild.id))
        await interaction.response.edit_message(embed=embed)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class PlatformSetup(commands.Cog):
    """Universal platform setup cog, driven by one panel command."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="platforms", description="Manage platform integrations (YouTube, Twitch, etc.)")
    @app_commands.default_permissions(administrator=True)
    async def platforms_panel(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        embed = await build_platforms_embed(self.bot, guild_id)
        view = PlatformDashboard(self.bot, guild_id)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(PlatformSetup(bot))