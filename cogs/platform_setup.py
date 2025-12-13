# cogs/platform_setup.py
import discord
from discord import app_commands
from discord.ext import commands

class PlatformSetup(commands.Cog):
    """Universal platform setup cog with a single command"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="setup_platform", description="Setup any platform for tracking")
    @app_commands.describe(
        platform="Platform to setup",
        api_key="Main API key/credential (YouTube API key or Twitch Client ID)",
        secret_key="Secret/Additional key (Twitch Client Secret only)"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch")
    ])
    @app_commands.default_permissions(administrator=True)
    async def setup_platform(self, interaction: discord.Interaction, platform: str, api_key: str, secret_key: str = None):
        """Universal platform setup command"""
        await interaction.response.defer(ephemeral=True)
        
        # Get platform instance
        platform_lower = platform.lower()
        platform_instance = None
        
        if platform_lower == "youtube":
            platform_instance = self.bot.youtube_platform
        elif platform_lower == "twitch":
            platform_instance = self.bot.twitch_platform
        
        if not platform_instance:
            await interaction.followup.send(
                f"❌ Platform **{platform}** is not available.",
                ephemeral=True
            )
            return
        
        # Call platform-specific setup
        success = False
        if platform_lower == "youtube":
            success = await platform_instance._setup_youtube(interaction, api_key)
        elif platform_lower == "twitch":
            if not secret_key:
                await interaction.followup.send(
                    "❌ Twitch requires both Client ID and Client Secret.\n"
                    "Please provide your Client ID as api_key and Client Secret as secret_key.",
                    ephemeral=True
                )
                return
            success = await platform_instance._setup_twitch(interaction, api_key, secret_key)
        
        if success:
            # Store configured platforms
            if not hasattr(self.bot, 'configured_platforms'):
                self.bot.configured_platforms = {}
            
            guild_id = str(interaction.guild.id)
            if guild_id not in self.bot.configured_platforms:
                self.bot.configured_platforms[guild_id] = []
            
            if platform_lower not in self.bot.configured_platforms[guild_id]:
                self.bot.configured_platforms[guild_id].append(platform_lower)
    
    @app_commands.command(name="list_platforms", description="List all configured platforms")
    async def list_platforms(self, interaction: discord.Interaction):
        """List configured platforms"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        configured = []
        
        # Check YouTube
        if self.bot.youtube_platform and self.bot.youtube_platform.is_configured(guild_id):
            configured.append("🎥 YouTube")
        
        # Check Twitch
        if self.bot.twitch_platform and self.bot.twitch_platform.is_configured(guild_id):
            configured.append("🟣 Twitch")
        
        if not configured:
            await interaction.followup.send("❌ No platforms configured yet.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🌐 Configured Platforms",
            description=f"**{len(configured)}** platform(s) configured",
            color=discord.Color.blue()
        )
        embed.add_field(name="Active Platforms", value="\n".join(configured), inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="remove_platform", description="Remove a platform configuration")
    @app_commands.describe(platform="Platform to remove")
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch")
    ])
    @app_commands.default_permissions(administrator=True)
    async def remove_platform(self, interaction: discord.Interaction, platform: str):
        """Remove a platform configuration"""
        await interaction.response.defer(ephemeral=True)
        
        platform_lower = platform.lower()
        guild_id = str(interaction.guild.id)
        
        # Get platform instance
        platform_instance = None
        if platform_lower == "youtube":
            platform_instance = self.bot.youtube_platform
        elif platform_lower == "twitch":
            platform_instance = self.bot.twitch_platform
        
        if not platform_instance:
            await interaction.followup.send(f"❌ Platform **{platform}** is not available.", ephemeral=True)
            return
        
        # Check if platform is configured
        if not platform_instance.is_configured(guild_id):
            await interaction.followup.send(f"❌ Platform **{platform}** is not configured for this server.", ephemeral=True)
            return
        
        # Remove configuration
        success = platform_instance.remove_config(guild_id)
        
        if success:
            # Remove from bot's configured platforms
            if hasattr(self.bot, 'configured_platforms') and guild_id in self.bot.configured_platforms:
                if platform_lower in self.bot.configured_platforms[guild_id]:
                    self.bot.configured_platforms[guild_id].remove(platform_lower)
            
            await interaction.followup.send(f"✅ Removed **{platform}** configuration.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to remove **{platform}** configuration.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PlatformSetup(bot))