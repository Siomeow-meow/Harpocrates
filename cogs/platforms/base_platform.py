# cogs/platforms/base_platform.py
import discord
from discord import app_commands
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime

class BasePlatform(ABC):
    """Abstract base class for all platform integrations - NOT a Cog"""
    
    def __init__(self, bot, platform_name):
        self.bot = bot
        self.platform_name = platform_name.lower()
        self.platforms_file = "data/platforms.json"
        self.platforms = self._load_platforms()
    
    def _load_platforms(self):
        """Load platform configurations"""
        if os.path.exists(self.platforms_file):
            try:
                with open(self.platforms_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                print(f"⚠️ Error loading {self.platforms_file}, creating new file")
                return {}
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.platforms_file), exist_ok=True)
        return {}
    
    def _save_platforms(self):
        """Save platform configurations"""
        try:
            os.makedirs(os.path.dirname(self.platforms_file), exist_ok=True)
            with open(self.platforms_file, 'w') as f:
                json.dump(self.platforms, f, indent=4)
            print(f"✅ Saved platforms to {self.platforms_file}")
        except Exception as e:
            print(f"❌ Error saving platforms: {e}")
    
    def is_configured(self, guild_id):
        """Check if platform is configured for a guild"""
        guild_id = str(guild_id)
        return guild_id in self.platforms and self.platform_name in self.platforms[guild_id]
    
    def get_config(self, guild_id):
        """Get platform configuration for a guild"""
        guild_id = str(guild_id)
        if self.is_configured(guild_id):
            return self.platforms[guild_id][self.platform_name]
        return None
    
    def remove_config(self, guild_id):
        """Remove platform configuration for a guild"""
        guild_id = str(guild_id)
        if guild_id in self.platforms and self.platform_name in self.platforms[guild_id]:
            del self.platforms[guild_id][self.platform_name]
            # Remove guild entry if empty
            if not self.platforms[guild_id]:
                del self.platforms[guild_id]
            self._save_platforms()
            return True
        return False
    
    @abstractmethod
    async def setup_command(self, interaction: discord.Interaction, **kwargs):
        """Platform-specific setup command"""
        pass
    
    @abstractmethod
    async def get_channel_id(self, creator_input: str, guild_id: int):
        """Convert creator handle to platform channel ID"""
        pass
    
    @abstractmethod
    async def get_channel_info(self, channel_id: str, guild_id: int):
        """Get channel information"""
        pass
    
    @abstractmethod
    async def get_latest_content(self, channel_id: str, guild_id: int):
        """Get latest content from channel"""
        pass
    
    @abstractmethod
    async def get_content_description(self, content_id: str, guild_id: int):
        """Get content description"""
        pass