import discord
from discord.ext import commands
from discord import app_commands
from apikeys import BOTTOKEN, SERVERID
import logging
import sys
import asyncio
import os

# Prevent __pycache__ generation
sys.dont_write_bytecode = True


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix='?',
            intents=intents,
        )

        self.logger = self._setup_logger()
        self.youtube_platform = None
        self.twitch_platform = None
        self.synced_guilds = set()

        # Create data folder if it doesn't exist
        if not os.path.exists('data'):
            os.makedirs('data')
            self.logger.info("Created data folder")

    def _setup_logger(self):
        logger = logging.getLogger('discord.bot')
        logger.setLevel(logging.INFO)

        # Prevent duplicate handlers
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
            logger.addHandler(handler)

        return logger

    async def setup_hook(self):
        """Setup all cogs when bot starts"""
        self.logger.info("Starting bot setup...")

        # ─────────────────────────────────────────────
        # 1. Load platform modules FIRST (not cogs)
        # ─────────────────────────────────────────────
        self.logger.info("Loading platform modules...")

        try:
            from cogs.platforms.youtube import YouTubePlatform
            self.youtube_platform = YouTubePlatform(self)
            self.logger.info("✅ YouTube platform loaded")
        except Exception as e:
            self.logger.error(f"❌ Failed to load YouTube platform: {e}")

        try:
            from cogs.platforms.twitch import TwitchPlatform
            self.twitch_platform = TwitchPlatform(self)
            self.logger.info("✅ Twitch platform loaded")
        except Exception as e:
            self.logger.error(f"❌ Failed to load Twitch platform: {e}")

        # ─────────────────────────────────────────────
        # 2. Load all cogs
        # ─────────────────────────────────────────────
        cogs_to_load = [
            'voice',
            'help',
            'reaction-role',
            'platform_setup',
            'creator-videos'
        ]

        for cog_name in cogs_to_load:
            try:
                await self.load_extension(f'cogs.{cog_name}')
                self.logger.info(f"✅ Loaded cog: {cog_name}")
            except Exception as e:
                self.logger.error(f"❌ Failed to load cog {cog_name}: {e}")

        # ─────────────────────────────────────────────
        # 3. Register platforms
        # ─────────────────────────────────────────────
        await self.register_platforms()

        # ─────────────────────────────────────────────
        # 4. Sync slash commands (SAFE)
        # ─────────────────────────────────────────────
        await self.auto_sync_commands()

        self.logger.info("=" * 50)

    async def auto_sync_commands(self):
        """Sync slash commands safely after cleanup"""
        guild_id = SERVERID

        if guild_id in self.synced_guilds:
            self.logger.info("Commands already synced, skipping...")
            return

        self.logger.info("Syncing application commands...")

        try:
            guild = discord.Object(id=guild_id)

            # 🔥 IMPORTANT:
            # Copy all global commands registered by cogs
            # into the guild before syncing
            self.tree.copy_global_to(guild=guild)

            synced = await self.tree.sync(guild=guild)

            self.logger.info(
                f"✅ Successfully synced {len(synced)} command(s) to guild {guild_id}"
            )

            self.synced_guilds.add(guild_id)

        except Exception as e:
            self.logger.error(f"❌ Failed to sync commands: {e}")

    async def register_platforms(self):
        """Register platforms with creator-videos cog"""
        creator_cog = self.get_cog('CreatorVideos')

        if not creator_cog:
            self.logger.error("❌ CreatorVideos cog not found!")
            return

        if self.youtube_platform:
            creator_cog.register_platform('youtube', self.youtube_platform)
        else:
            self.logger.error("❌ YouTube platform not available!")

        if self.twitch_platform:
            creator_cog.register_platform('twitch', self.twitch_platform)
        else:
            self.logger.error("❌ Twitch platform not available!")

    async def on_ready(self):
        self.logger.info(f"✅ Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info(f"✅ Connected to {len(self.guilds)} guild(s)")


# ─────────────────────────────────────────────
# Global slash-command error handler
# ─────────────────────────────────────────────
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CommandSignatureMismatch):
        await interaction.response.send_message(
            "⚠️ Command signature mismatch. Please contact the bot administrator.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(error)}",
            ephemeral=True
        )


if __name__ == "__main__":
    bot = MyBot()
    bot.tree.on_error = on_app_command_error
    bot.run(BOTTOKEN)
