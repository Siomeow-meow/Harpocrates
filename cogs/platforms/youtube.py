# cogs/platforms/youtube.py
import discord
from discord import app_commands
from discord.ext import commands
from googleapiclient.discovery import build
from .base_platform import BasePlatform
import re
import time
from datetime import datetime

class YouTubePlatform(BasePlatform):
    """YouTube platform integration"""
    
    def __init__(self, bot):
        super().__init__(bot, "youtube")
        self.bot = bot
        self.clients = {}
        self.cache = {}
        self.CACHE_DURATION = 6 * 60 * 60  # 6 hours
        self.platform_icon = "🎥"
        
        # Initialize clients from saved configurations on startup
        self.restore_clients_from_config()
    
    def restore_clients_from_config(self):
        """Restore YouTube clients from saved configurations on startup"""
        print("🔄 Restoring YouTube clients from saved configurations...")
        
        restored = 0
        failed = 0
        
        for guild_id, guild_data in self.platforms.items():
            if 'youtube' in guild_data:
                youtube_config = guild_data['youtube']
                api_key = youtube_config.get('api_key')
                
                if api_key:
                    # Try to initialize client
                    if self._initialize_client(guild_id, api_key, silent=True):
                        print(f"✅ Restored YouTube client for guild {guild_id}")
                        restored += 1
                    else:
                        print(f"❌ Failed to restore YouTube client for guild {guild_id}")
                        failed += 1
        
        print(f"📊 YouTube clients restored: {restored} successful, {failed} failed")
    
    def _initialize_client(self, guild_id, api_key, silent=False):
        """Initialize YouTube API client"""
        guild_id = str(guild_id)
        try:
            self.clients[guild_id] = build('youtube', 'v3', developerKey=api_key)
            if not silent:
                print(f"✅ Initialized YouTube client for guild {guild_id}")
            return True
        except Exception as e:
            if not silent:
                print(f"❌ Failed to initialize YouTube client for guild {guild_id}: {e}")
            return False
    
    def get_client(self, guild_id):
        """Get YouTube client for guild"""
        guild_id = str(guild_id)
        
        # First, try to get existing client
        if guild_id in self.clients:
            return self.clients[guild_id]
        
        # If no client exists but config exists, try to initialize it
        if self.is_configured(guild_id):
            config = self.get_config(guild_id)
            api_key = config.get('api_key')
            
            if api_key:
                print(f"🔄 Lazy-initializing YouTube client for guild {guild_id}")
                if self._initialize_client(guild_id, api_key):
                    return self.clients.get(guild_id)
                else:
                    print(f"❌ Failed to lazy-initialize YouTube client for guild {guild_id}")
        
        return None
    
    def is_cache_valid(self, cache_timestamp):
        """Check if cache is still valid"""
        if not cache_timestamp:
            return False
        return (time.time() - cache_timestamp) < self.CACHE_DURATION
    
    # ========== SETUP METHOD ==========
    
    async def _setup_youtube(self, interaction: discord.Interaction, api_key: str):
        """Setup YouTube API for this server - called by universal setup_platform"""
        guild_id = str(interaction.guild.id)
        
        # Test the API key by initializing client
        if not self._initialize_client(guild_id, api_key):
            await interaction.followup.send("❌ Invalid YouTube API key. Please check and try again.", ephemeral=True)
            return False
        
        # Store YouTube configuration
        if guild_id not in self.platforms:
            self.platforms[guild_id] = {}
        
        self.platforms[guild_id][self.platform_name] = {
            "api_key": api_key,
            "setup_by": interaction.user.id,
            "setup_at": datetime.now().isoformat()
        }
        
        # Save to file
        self._save_platforms()
        
        embed = discord.Embed(
            title=f"✅ {self.platform_icon} YouTube Setup Complete",
            description="YouTube has been configured for this server.",
            color=discord.Color.red()
        )
        embed.add_field(name="Platform", value="YouTube", inline=True)
        embed.add_field(name="Status", value="✅ Active", inline=True)
        embed.set_footer(text="You can now use /follow with YouTube creators")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        return True
    
    # ========== PLATFORM METHODS ==========
    
    async def setup_command(self, interaction: discord.Interaction, **kwargs):
        """Handle platform setup - implements abstract method"""
        api_key = kwargs.get('api_key')
        if not api_key:
            await interaction.followup.send("❌ API key is required for YouTube setup.", ephemeral=True)
            return
        
        return await self._setup_youtube(interaction, api_key)
    
    async def get_channel_id(self, creator_input: str, guild_id: int):
        """Convert @handle or channel ID into a proper channel ID"""
        youtube = self.get_client(guild_id)
        if not youtube:
            # Try to initialize from config
            if not self.is_configured(guild_id):
                print(f"❌ YouTube not configured for guild {guild_id}")
                return None
            
            # Try to get client one more time
            youtube = self.get_client(guild_id)
            if not youtube:
                print(f"❌ Failed to initialize YouTube client for guild {guild_id}")
                return None
        
        try:
            if creator_input.startswith("UC") and len(creator_input) == 24:
                return creator_input
            
            cache_key = f"youtube_channel_id_{creator_input}"
            if cache_key in self.cache:
                data, timestamp = self.cache[cache_key]
                if self.is_cache_valid(timestamp):
                    return data
            
            query = creator_input.lstrip('@')
            
            if creator_input.startswith('@'):
                try:
                    request = youtube.channels().list(
                        part="snippet",
                        forHandle=query
                    )
                    response = request.execute()
                    if response.get("items"):
                        channel_id = response["items"][0]["id"]
                        self.cache[cache_key] = (channel_id, time.time())
                        return channel_id
                except Exception:
                    pass
            
            request = youtube.search().list(
                part="snippet",
                q=query,
                type="channel",
                maxResults=5
            )
            response = request.execute()
            
            if not response.get("items"):
                return None
            
            best_match = None
            for item in response["items"]:
                snippet = item["snippet"]
                channel_title = snippet["title"].lower()
                channel_description = snippet.get("description", "").lower()
                
                if (f"@{query.lower()}" in channel_title or 
                    query.lower() in channel_title or
                    query.lower() in channel_description):
                    best_match = item
                    break
            
            if not best_match and response["items"]:
                best_match = response["items"][0]
            
            if best_match:
                channel_id = best_match["snippet"]["channelId"]
                self.cache[cache_key] = (channel_id, time.time())
                return channel_id
            
            return None
            
        except Exception as e:
            print(f"Error fetching YouTube channel ID: {e}")
            return None
    
    async def get_channel_info(self, channel_id: str, guild_id: int):
        """Get YouTube channel info"""
        youtube = self.get_client(guild_id)
        if not youtube:
            return None
        
        try:
            cache_key = f"youtube_info_{channel_id}"
            if cache_key in self.cache:
                data, timestamp = self.cache[cache_key]
                if self.is_cache_valid(timestamp):
                    return data
            
            request = youtube.channels().list(part="snippet", id=channel_id)
            response = request.execute()
            
            if not response.get("items"):
                return None
            
            channel_info = response["items"][0]
            self.cache[cache_key] = (channel_info, time.time())
            return channel_info
            
        except Exception as e:
            print(f"Error fetching YouTube channel info: {e}")
            return None
    
    async def get_latest_content(self, channel_id: str, guild_id: int):
        """Get latest video from YouTube channel"""
        youtube = self.get_client(guild_id)
        if not youtube:
            return None
        
        try:
            cache_key = f"youtube_latest_{channel_id}"
            if cache_key in self.cache:
                data, timestamp = self.cache[cache_key]
                if self.is_cache_valid(timestamp):
                    return data
            
            request = youtube.search().list(
                part="snippet",
                channelId=channel_id,
                maxResults=1,
                order="date",
                type="video"
            )
            response = request.execute()
            
            if not response.get("items"):
                return None
            
            latest_video = response["items"][0]
            
            # Verify it's from the correct channel
            video_channel_id = latest_video["snippet"]["channelId"]
            if video_channel_id != channel_id:
                return None
            
            self.cache[cache_key] = (latest_video, time.time())
            return latest_video
            
        except Exception as e:
            print(f"Error fetching YouTube latest video: {e}")
            return None
    
    async def get_content_description(self, content_id: str, guild_id: int):
        """Get YouTube video description"""
        youtube = self.get_client(guild_id)
        if not youtube:
            return None
        
        try:
            cache_key = f"youtube_desc_{content_id}"
            if cache_key in self.cache:
                data, timestamp = self.cache[cache_key]
                if self.is_cache_valid(timestamp):
                    return data.get("description")
            
            request = youtube.videos().list(part="snippet", id=content_id)
            response = request.execute()
            
            if not response.get("items"):
                return None
            
            description = response["items"][0]["snippet"]["description"]
            self.cache[cache_key] = ({"description": description}, time.time())
            return description
            
        except Exception:
            return None
    
    def clean_description(self, description: str) -> str:
        """Remove embeddable links from description"""
        if not description:
            return ""
        return re.sub(r'(https?://\S+)', lambda m: f'<{m.group(1)}>', description)

async def setup(bot):
    platform = YouTubePlatform(bot)
    return platform