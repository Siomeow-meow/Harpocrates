# cogs/platforms/twitch.py
import discord
from discord import app_commands
from discord.ext import commands
from .base_platform import BasePlatform
import aiohttp
import json
import time
from datetime import datetime

class TwitchPlatform(BasePlatform):
    """Twitch platform integration"""
    
    def __init__(self, bot):
        super().__init__(bot, "twitch")
        self.bot = bot
        self.access_tokens = {}
        self.cache = {}
        self.CACHE_DURATION = 2 * 60 * 60  # 2 hours for Twitch
        self.TWITCH_API_BASE = "https://api.twitch.tv/helix"
        self.platform_icon = "🟣"
        
        # Restore access tokens from saved configurations
        self.restore_tokens_from_config()
    
    def restore_tokens_from_config(self):
        """Restore Twitch access tokens from saved configurations on startup"""
        print("🔄 Restoring Twitch tokens from saved configurations...")
        
        restored = 0
        needs_refresh = 0
        
        for guild_id, guild_data in self.platforms.items():
            if 'twitch' in guild_data:
                twitch_config = guild_data['twitch']
                client_id = twitch_config.get('client_id')
                client_secret = twitch_config.get('client_secret')
                saved_token = twitch_config.get('access_token')
                
                if client_id and saved_token:
                    # Store the saved token for now
                    self.access_tokens[guild_id] = saved_token
                    print(f"✅ Restored Twitch token for guild {guild_id}")
                    restored += 1
                elif client_id and client_secret:
                    # We have credentials but no token - we'll get one lazily
                    print(f"⚠️ Twitch credentials found for guild {guild_id}, will get token when needed")
                    needs_refresh += 1
        
        print(f"📊 Twitch tokens restored: {restored} from cache, {needs_refresh} need refresh")
    
    async def _get_access_token(self, client_id, client_secret):
        """Get OAuth access token from Twitch"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "grant_type": "client_credentials"
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        token = data.get("access_token")
                        if token:
                            print(f"✅ Got new Twitch access token")
                            return token
        except Exception as e:
            print(f"Error getting Twitch access token: {e}")
        return None
    
    def is_cache_valid(self, cache_timestamp):
        """Check if cache is still valid"""
        if not cache_timestamp:
            return False
        return (time.time() - cache_timestamp) < self.CACHE_DURATION
    
    async def _ensure_access_token(self, guild_id):
        """Ensure we have a valid access token for the guild"""
        guild_id = str(guild_id)
        
        # Check if we have a token in memory
        if guild_id in self.access_tokens:
            # Test if token is still valid
            config = self.get_config(guild_id)
            if config:
                client_id = config.get('client_id')
                token = self.access_tokens[guild_id]
                
                if await self._test_twitch_api(client_id, token):
                    return token
                else:
                    print(f"⚠️ Twitch token for guild {guild_id} is invalid, refreshing...")
                    # Token is invalid, remove it
                    del self.access_tokens[guild_id]
        
        # Get config to create/refresh token
        config = self.get_config(guild_id)
        if not config:
            print(f"❌ No Twitch config for guild {guild_id}")
            return None
        
        client_id = config.get('client_id')
        client_secret = config.get('client_secret')
        
        if not client_id or not client_secret:
            print(f"❌ Incomplete Twitch config for guild {guild_id}")
            return None
        
        # Get new token
        new_token = await self._get_access_token(client_id, client_secret)
        if not new_token:
            print(f"❌ Failed to get Twitch token for guild {guild_id}")
            return None
        
        # Store in memory
        self.access_tokens[guild_id] = new_token
        
        # Update config with new token
        config['access_token'] = new_token
        self.platforms[guild_id][self.platform_name] = config
        self._save_platforms()
        
        print(f"✅ Updated Twitch token for guild {guild_id}")
        return new_token
    
    async def _test_twitch_api(self, client_id, access_token):
        """Test Twitch API credentials"""
        try:
            headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {access_token}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.TWITCH_API_BASE}/users",
                    headers=headers,
                    params={"login": "twitch"}  # Test with a known user
                ) as response:
                    if response.status == 200:
                        return True
                    else:
                        print(f"❌ Twitch API test failed: HTTP {response.status}")
                        return False
        except Exception as e:
            print(f"❌ Twitch API test error: {e}")
            return False
    
    # ========== SETUP METHOD ==========
    
    async def _setup_twitch(self, interaction: discord.Interaction, client_id: str, client_secret: str):
        """Setup Twitch API for this server - called by universal setup_platform"""
        guild_id = str(interaction.guild.id)
        
        # Try to get access token
        access_token = await self._get_access_token(client_id, client_secret)
        if not access_token:
            await interaction.followup.send(
                "❌ Failed to get Twitch access token. Please check your client ID and secret.",
                ephemeral=True
            )
            return False
        
        # Test the API credentials
        test_success = await self._test_twitch_api(client_id, access_token)
        if not test_success:
            await interaction.followup.send(
                "❌ Invalid Twitch credentials. Please check and try again.",
                ephemeral=True
            )
            return False
        
        # Initialize guild entry if not exists
        if guild_id not in self.platforms:
            self.platforms[guild_id] = {}
        
        # Store Twitch configuration
        self.platforms[guild_id][self.platform_name] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "access_token": access_token,
            "setup_by": interaction.user.id,
            "setup_at": datetime.now().isoformat()
        }
        
        # Store token in memory
        self.access_tokens[guild_id] = access_token
        
        # Save to file
        self._save_platforms()
        
        embed = discord.Embed(
            title=f"✅ {self.platform_icon} Twitch Setup Complete",
            description="Twitch has been configured for this server.",
            color=discord.Color.purple()
        )
        embed.add_field(name="Platform", value="Twitch", inline=True)
        embed.add_field(name="Status", value="✅ Active", inline=True)
        embed.set_footer(text="You can now use /follow with Twitch creators")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        return True
    
    # ========== PLATFORM METHODS ==========
    
    async def setup_command(self, interaction: discord.Interaction, **kwargs):
        """Handle platform setup - implements abstract method"""
        api_key = kwargs.get('api_key')  # This is client_id
        additional_field = kwargs.get('additional_field')  # This is client_secret
        
        if not api_key or not additional_field:
            await interaction.followup.send(
                "❌ For Twitch, you need both Client ID and Client Secret.\n"
                "Format: `/setup_platform platform:Twitch api_key:CLIENT_ID additional_field:CLIENT_SECRET`",
                ephemeral=True
            )
            return False
        
        return await self._setup_twitch(interaction, api_key, additional_field)
    
    async def get_channel_id(self, creator_input: str, guild_id: int):
        """Convert username to Twitch user ID"""
        # Ensure we have access token
        access_token = await self._ensure_access_token(guild_id)
        if not access_token:
            print(f"❌ No Twitch access token for guild {guild_id}")
            return None
        
        config = self.get_config(guild_id)
        if not config:
            return None
        
        cache_key = f"twitch_user_id_{creator_input}"
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if self.is_cache_valid(timestamp):
                return data
        
        try:
            headers = {
                "Client-ID": config["client_id"],
                "Authorization": f"Bearer {access_token}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.TWITCH_API_BASE}/users",
                    headers=headers,
                    params={"login": creator_input.lstrip('@').lower()}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("data"):
                            user_id = data["data"][0]["id"]
                            self.cache[cache_key] = (user_id, time.time())
                            return user_id
                    else:
                        print(f"❌ Twitch API error getting user ID: HTTP {response.status}")
                        if response.status == 401:  # Unauthorized - token expired
                            print(f"⚠️ Token expired for guild {guild_id}, will refresh on next attempt")
                            # Remove invalid token
                            if str(guild_id) in self.access_tokens:
                                del self.access_tokens[str(guild_id)]
        except Exception as e:
            print(f"Error fetching Twitch user ID: {e}")
        
        return None
    
    async def get_channel_info(self, channel_id: str, guild_id: int):
        """Get Twitch channel info"""
        access_token = await self._ensure_access_token(guild_id)
        if not access_token:
            return None
        
        config = self.get_config(guild_id)
        if not config:
            return None
        
        cache_key = f"twitch_info_{channel_id}"
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if self.is_cache_valid(timestamp):
                return data
        
        try:
            headers = {
                "Client-ID": config["client_id"],
                "Authorization": f"Bearer {access_token}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.TWITCH_API_BASE}/users",
                    headers=headers,
                    params={"id": channel_id}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("data"):
                            channel_info = data["data"][0]
                            self.cache[cache_key] = (channel_info, time.time())
                            return channel_info
        except Exception as e:
            print(f"Error fetching Twitch channel info: {e}")
        
        return None
    
    async def get_latest_content(self, channel_id: str, guild_id: int):
        """Check if channel is currently streaming"""
        access_token = await self._ensure_access_token(guild_id)
        if not access_token:
            return None
        
        config = self.get_config(guild_id)
        if not config:
            return None
        
        cache_key = f"twitch_stream_{channel_id}"
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if self.is_cache_valid(timestamp):
                return data
        
        try:
            headers = {
                "Client-ID": config["client_id"],
                "Authorization": f"Bearer {access_token}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.TWITCH_API_BASE}/streams",
                    headers=headers,
                    params={"user_id": channel_id}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        stream_data = data.get("data", [])
                        if stream_data:
                            # Channel is live
                            stream_info = stream_data[0]
                            self.cache[cache_key] = (stream_info, time.time())
                            return stream_info
                        else:
                            # Channel is offline
                            self.cache[cache_key] = (None, time.time())
                            return None
        except Exception as e:
            print(f"Error checking Twitch stream: {e}")
        
        return None
    
    async def get_content_description(self, content_id: str, guild_id: int):
        """Get stream description (not applicable for Twitch live streams)"""
        # For Twitch, we get the stream info directly in get_latest_content
        return None

async def setup(bot):
    platform = TwitchPlatform(bot)
    return platform