import discord
from discord import app_commands
from abc import ABC, abstractmethod
from datetime import datetime
from db import load_blob, save_blob

COLLECTION = "platforms"

class BasePlatform(ABC):

    def __init__(self, bot, platform_name):
        self.bot = bot
        self.platform_name = platform_name.lower()
        self.platforms = self._load_platforms()

    def _load_platforms(self):
        try:
            return load_blob(COLLECTION)
        except Exception as e:
            print(f"⚠️ Error loading platforms from MongoDB: {e}")
            return {}

    def _save_platforms(self):
        try:
            success = save_blob(COLLECTION, self.platforms)
            print(f"{'✅ Saved platforms to MongoDB' if success else '❌ Failed to save platforms'}")
        except Exception as e:
            print(f"❌ Error saving platforms: {e}")

    def is_configured(self, guild_id):
        guild_id = str(guild_id)
        return guild_id in self.platforms and self.platform_name in self.platforms[guild_id]

    def get_config(self, guild_id):
        guild_id = str(guild_id)
        if self.is_configured(guild_id):
            return self.platforms[guild_id][self.platform_name]
        return None

    def remove_config(self, guild_id):
        guild_id = str(guild_id)
        if guild_id in self.platforms and self.platform_name in self.platforms[guild_id]:
            del self.platforms[guild_id][self.platform_name]

            if not self.platforms[guild_id]:
                del self.platforms[guild_id]
            self._save_platforms()
            return True
        return False

    @abstractmethod
    async def setup_command(self, interaction: discord.Interaction, **kwargs):
        pass

    @abstractmethod
    async def get_channel_id(self, creator_input: str, guild_id: int):
        pass

    @abstractmethod
    async def get_channel_info(self, channel_id: str, guild_id: int):
        pass

    @abstractmethod
    async def get_latest_content(self, channel_id: str, guild_id: int):
        pass

    @abstractmethod
    async def get_content_description(self, content_id: str, guild_id: int):
        pass
