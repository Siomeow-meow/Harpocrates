# cogs/creator-videos.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import re
import time
from datetime import datetime, timedelta
import asyncio

TRACKED_FILE = "data/tracked_channels.json"
CACHE_DURATION = 15 * 60  # 15 minutes

class CreatorVideos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.platforms = {}  # Will store platform instances
        self.cache = {}
        self.tracked_channels = self.load_tracked_channels()  # Load into instance
        
        # Track initialization state
        self.initialized = False
        
        self.check_uploads.start()
    
    def load_tracked_channels(self):
        """Load existing tracked channels or create empty dict"""
        # Create data directory if it doesn't exist
        os.makedirs(os.path.dirname(TRACKED_FILE), exist_ok=True)
        
        if os.path.exists(TRACKED_FILE):
            try:
                with open(TRACKED_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
            except (json.JSONDecodeError, ValueError) as e:
                print(f"❌ Error loading {TRACKED_FILE}: {e}")
                # Create backup of corrupted file
                backup_file = TRACKED_FILE + '.corrupted'
                try:
                    os.rename(TRACKED_FILE, backup_file)
                    print(f"⚠️ Created backup of corrupted file: {backup_file}")
                except:
                    pass
                return {}
        else:
            print(f"⚠️ No tracked channels file found at {TRACKED_FILE}, creating new one")
            return {}
    
    def save_tracked_channels(self):
        """Save current tracking data to JSON file with proper error handling"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(TRACKED_FILE), exist_ok=True)
            
            # Write to temporary file first to prevent corruption
            temp_file = TRACKED_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.tracked_channels, f, indent=4, sort_keys=True, ensure_ascii=False)
            
            # Replace the old file with the new one
            if os.path.exists(TRACKED_FILE):
                # Create backup
                backup_file = TRACKED_FILE + '.bak'
                try:
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(TRACKED_FILE, backup_file)
                except:
                    pass
            
            # Rename temp file to actual file
            os.rename(temp_file, TRACKED_FILE)
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving tracked channels: {e}")
            return False
    
    def register_platform(self, platform_name, platform_instance):
        """Register a platform instance"""
        self.platforms[platform_name.lower()] = platform_instance
        print(f"✅ Registered platform: {platform_name}")
    
    def get_platform(self, platform_name):
        """Get platform instance by name"""
        return self.platforms.get(platform_name.lower())
    
    def cog_unload(self):
        self.check_uploads.cancel()
    
    async def restore_roles_on_startup(self):
        """Restore roles to users when bot starts up"""
        print("Restoring roles on startup...")
        for creator_key, data in list(self.tracked_channels.items()):
            user_id = data.get("user_id")
            role_id = data.get("role_id")
            
            if user_id and role_id:
                for guild in self.bot.guilds:
                    user = guild.get_member(user_id)
                    role = guild.get_role(role_id)
                    
                    if user and role:
                        try:
                            if role not in user.roles:
                                await user.add_roles(role)
                                print(f"Restored role {role.name} to {user.display_name}")
                        except discord.Forbidden:
                            print(f"Missing permissions to restore role for {user.display_name}")
                        except Exception as e:
                            print(f"Error restoring role: {e}")
    
    def clean_description(self, description: str) -> str:
        """Remove embeddable links from description"""
        if not description:
            return ""
        return re.sub(r'(https?://\S+)', lambda m: f'<{m.group(1)}>', description)
    
    def is_cache_valid(self, cache_timestamp):
        """Check if cache is still valid"""
        if not cache_timestamp:
            return False
        return (time.time() - cache_timestamp) < CACHE_DURATION
    
    @tasks.loop(minutes=30)
    async def check_uploads(self):
        """Check for new content from tracked channels"""
        if not self.tracked_channels:
            return

        if not self.initialized:
            self.initialized = True
            return

        for creator_key, data in list(self.tracked_channels.items()):
            platform_name = data.get("platform")
            guild_id = data.get("guild_id")
            discord_channel_id = data.get("discord_channel_id")
            
            if not guild_id or not discord_channel_id:
                continue
            
            discord_channel = self.bot.get_channel(discord_channel_id)
            if not discord_channel:
                continue

            try:
                platform = self.get_platform(platform_name)
                if not platform:
                    print(f"❌ Platform {platform_name} not found for creator {creator_key}")
                    continue
                
                creator_id = data.get("creator_id")
                if not creator_id:
                    continue
                
                if platform_name == "youtube":
                    latest_video = await platform.get_latest_content(creator_id, guild_id)
                    if not latest_video:
                        continue

                    video_id = latest_video["id"]["videoId"]
                    
                    if "last_content_id" in data and data["last_content_id"] == video_id:
                        continue

                    self.tracked_channels[creator_key]["last_content_id"] = video_id
                    self.save_tracked_channels()

                    video_url = f"https://youtube.com/watch?v={video_id}"
                    description = await platform.get_content_description(video_id, guild_id) or "No description available"
                    
                    # Use platform's clean_description if available
                    if hasattr(platform, 'clean_description'):
                        description = platform.clean_description(description)
                    else:
                        description = self.clean_description(description)
                    
                    channel_title = latest_video['snippet']['channelTitle']
                    if latest_video["snippet"].get("liveBroadcastContent") == "live":
                        message = f"🎥 **{channel_title} is LIVE on YouTube!**\n\n{description}\n\n{video_url}"
                    else:
                        message = f"🎥 New video from **{channel_title} on YouTube!**\n\n{description}\n\n{video_url}"
                    
                    await discord_channel.send(message)
                
                elif platform_name == "twitch":
                    stream_info = await platform.get_latest_content(creator_id, guild_id)
                    if stream_info:
                        # Channel is live
                        stream_id = stream_info["id"]
                        
                        if "last_content_id" in data and data["last_content_id"] == stream_id:
                            continue
                        
                        self.tracked_channels[creator_key]["last_content_id"] = stream_id
                        self.save_tracked_channels()
                        
                        stream_url = f"https://twitch.tv/{data.get('creator_input', '').lstrip('@')}"
                        title = stream_info["title"]
                        game_name = stream_info.get("game_name", "Unknown Game")
                        viewer_count = stream_info.get("viewer_count", 0)
                        
                        message = f"🟣 **{data.get('creator_name', 'Unknown')} is LIVE on Twitch!**\n\n"
                        message += f"**Playing:** {game_name}\n"
                        message += f"**Title:** {title}\n"
                        message += f"**Viewers:** {viewer_count}\n\n"
                        message += stream_url
                        
                        await discord_channel.send(message)
                    else:
                        # Channel went offline
                        if "last_content_id" in data:
                            self.tracked_channels[creator_key]["last_content_id"] = None
                            self.save_tracked_channels()
                
                # Add more platforms here as needed
                
            except Exception as e:
                print(f"Error checking {platform_name} creator {creator_key}: {e}")
    
    @check_uploads.before_loop
    async def before_check_uploads(self):
        """Initialize before starting the loop"""
        await self.bot.wait_until_ready()
        
        await self.restore_roles_on_startup()
        
        # Initialize last content IDs
        for creator_key, data in list(self.tracked_channels.items()):
            platform_name = data.get("platform")
            guild_id = data.get("guild_id")
            creator_id = data.get("creator_id")
            
            if platform_name and guild_id and creator_id:
                platform = self.get_platform(platform_name)
                if platform and platform_name == "youtube":
                    latest_video = await platform.get_latest_content(creator_id, guild_id)
                    if latest_video:
                        self.tracked_channels[creator_key]["last_content_id"] = latest_video["id"]["videoId"]
        
        self.save_tracked_channels()
    
    # ========== CREATOR TRACKING COMMANDS ==========
    
    @app_commands.command(name="follow", description="Start getting notifications when a content creator uploads new content")
    @app_commands.describe(
        creator="The creator's @handle or ID (e.g., @pewdiepie or pewdiepie)",
        platform="Platform to track on",
        user="The Discord user to assign the role to (optional)",
        role="The role to assign to the user (optional)",
        channel="The Discord channel to notify (defaults to current channel)"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch")
    ])
    async def start_tracking(self, interaction: discord.Interaction, creator: str, platform: str, 
                            user: discord.Member = None, role: discord.Role = None, 
                            channel: discord.TextChannel = None):
        """Start tracking a content creator"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        target_channel = channel or interaction.channel
        
        # Get platform instance
        platform_instance = self.get_platform(platform)
        if not platform_instance:
            await interaction.followup.send(
                f"❌ Platform **{platform}** is not available.",
                ephemeral=True
            )
            return
        
        # Check if platform is configured
        if not platform_instance.is_configured(guild_id):
            await interaction.followup.send(
                f"❌ Platform **{platform}** is not configured for this server.\n"
                f"Use `/setup_platform` first to configure the API.",
                ephemeral=True
            )
            return
        
        # Get channel ID from platform
        creator_id = await platform_instance.get_channel_id(creator, guild_id)
        if not creator_id:
            await interaction.followup.send(f"❌ Couldn't find that {platform.title()} channel.", ephemeral=True)
            return
        
        # Get channel info
        channel_info = await platform_instance.get_channel_info(creator_id, guild_id)
        if not channel_info:
            await interaction.followup.send(f"❌ Couldn't fetch {platform.title()} channel information.", ephemeral=True)
            return
        
        # Extract creator name based on platform
        if platform == "youtube":
            creator_name = channel_info["snippet"]["title"]
            platform_icon = "🎥"
        elif platform == "twitch":
            creator_name = channel_info["display_name"]
            platform_icon = "🟣"
        else:
            creator_name = creator
            platform_icon = "📱"
        
        # Check permissions
        if not target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.followup.send(f"❌ No permission to send messages in {target_channel.mention}", ephemeral=True)
            return
        
        # Check user/role combination
        if (user and not role) or (role and not user):
            await interaction.followup.send("❌ Please provide both user and role, or neither.", ephemeral=True)
            return
        
        # Check if user already tracking
        if user and role:
            if not interaction.guild.me.guild_permissions.manage_roles:
                await interaction.followup.send("❌ I don't have permission to manage roles.", ephemeral=True)
                return
            
            if role >= interaction.guild.me.top_role:
                await interaction.followup.send("❌ I can't assign that role as it's higher than my highest role.", ephemeral=True)
                return
            
            for tracked_id, tracked_data in self.tracked_channels.items():
                if tracked_data.get("user_id") == user.id and tracked_data.get("guild_id") == guild_id:
                    await interaction.followup.send(f"❌ {user.mention} is already tracking another creator.", ephemeral=True)
                    return
        
        # Check if creator already tracked
        creator_key = f"{platform}_{creator_id}"
        if creator_key in self.tracked_channels:
            existing_data = self.tracked_channels[creator_key]
            if existing_data.get("guild_id") == guild_id:
                existing_channel = self.bot.get_channel(existing_data["discord_channel_id"])
                existing_user = interaction.guild.get_member(existing_data.get("user_id", 0))
                user_mention = existing_user.mention if existing_user else "another user"
                channel_mention = existing_channel.mention if existing_channel else "another channel"
                await interaction.followup.send(f"❌ **{creator_name}** is already being tracked by {user_mention} in {channel_mention}.", ephemeral=True)
                return
        
        # Get latest content for initialization
        last_content_id = None
        latest_content = await platform_instance.get_latest_content(creator_id, guild_id)
        if latest_content:
            if platform == "youtube":
                last_content_id = latest_content["id"]["videoId"]
            elif platform == "twitch":
                last_content_id = latest_content.get("id")
        
        # Prepare tracking data
        tracking_data = {
            "platform": platform,
            "guild_id": guild_id,
            "discord_channel_id": target_channel.id,
            "last_content_id": last_content_id,
            "creator_name": creator_name,
            "creator_input": creator,
            "creator_id": creator_id
        }
        
        # Add user and role data if provided
        if user and role:
            tracking_data["user_id"] = user.id
            tracking_data["role_id"] = role.id
        
        # Add to tracked channels and save
        self.tracked_channels[creator_key] = tracking_data
        
        # Save to file
        if self.save_tracked_channels():
            print(f"✅ Successfully saved tracked creator: {creator_name}")
        else:
            print(f"❌ Failed to save tracked creator: {creator_name}")
        
        # Assign role if user and role are provided
        if user and role:
            try:
                await user.add_roles(role)
                success_message = f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** in {target_channel.mention} and assigned {role.mention} to {user.mention}!"
            except discord.Forbidden:
                success_message = f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** in {target_channel.mention}, but couldn't assign role due to permissions."
            except Exception as e:
                success_message = f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** in {target_channel.mention}, but error assigning role: {e}"
        else:
            success_message = f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** in {target_channel.mention}!"
        
        await interaction.followup.send(success_message, ephemeral=True)
    
    @app_commands.command(name="unfollow", description="Stop tracking a content creator")
    @app_commands.describe(
        creator="The creator's @handle or ID",
        platform="Platform the creator is on",
        channel="Optional Discord channel to stop tracking in"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch")
    ])
    async def stop_tracking(self, interaction: discord.Interaction, creator: str, platform: str, 
                            channel: discord.TextChannel = None):
        """Stop tracking a content creator"""
        await interaction.response.defer(ephemeral=True)
        
        target_channel = channel or interaction.channel
        
        # Try to find the creator
        creator_key = None
        for key, data in self.tracked_channels.items():
            if (data.get("platform") == platform and 
                data.get("creator_input") == creator and
                data.get("guild_id") == interaction.guild.id and
                data.get("discord_channel_id") == target_channel.id):
                creator_key = key
                break
        
        if not creator_key:
            await interaction.followup.send(f"❌ Creator not tracked in {target_channel.mention} on {platform}", ephemeral=True)
            return
        
        data = self.tracked_channels[creator_key]
        user_id = data.get("user_id")
        role_id = data.get("role_id")
        creator_name = data.get("creator_name", "Unknown Creator")
        
        # Remove from tracking
        del self.tracked_channels[creator_key]
        
        # Save changes
        self.save_tracked_channels()
        
        # Remove role if exists
        if user_id and role_id:
            if not interaction.guild.me.guild_permissions.manage_roles:
                await interaction.followup.send(f"✅ Stopped tracking **{creator_name}** but couldn't remove role.", ephemeral=True)
                return
            
            try:
                user = interaction.guild.get_member(user_id)
                role = interaction.guild.get_role(role_id)
                
                if user and role:
                    await user.remove_roles(role)
                    await interaction.followup.send(f"✅ Stopped tracking **{creator_name}** on {platform} and removed role.", ephemeral=True)
                else:
                    await interaction.followup.send(f"✅ Stopped tracking **{creator_name}** on {platform}.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(f"✅ Stopped tracking **{creator_name}** on {platform}, but couldn't remove role.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"✅ Stopped tracking **{creator_name}** on {platform}, but error removing role: {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Stopped tracking **{creator_name}** on {platform}.", ephemeral=True)
    
    @app_commands.command(name="show_creators", description="Show all currently followed content creators")
    async def show_creators(self, interaction: discord.Interaction):
        """Show all tracked content creators"""
        guild_tracked = {k: v for k, v in self.tracked_channels.items() 
                        if v.get("guild_id") == interaction.guild.id}
        
        if not guild_tracked:
            await interaction.response.send_message("No content creators are currently being tracked.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📺 Tracked Content Creators", 
            color=0x5865F2
        )
        
        platforms_summary = {}
        
        for creator_key, data in guild_tracked.items():
            platform = data.get("platform", "Unknown")
            if platform not in platforms_summary:
                platforms_summary[platform] = []
            
            channel_name = data.get("creator_name", "Unknown Creator")
            discord_channel = self.bot.get_channel(data["discord_channel_id"])
            user = interaction.guild.get_member(data.get("user_id", 0))
            role = interaction.guild.get_role(data.get("role_id", 0))
            
            entry = f"**{channel_name}**"
            if discord_channel:
                entry += f"\n↳ Notifying in {discord_channel.mention}"
            if user and role:
                entry += f"\n↳ User: {user.mention}, Role: {role.mention}"
            elif user:
                entry += f"\n↳ User: {user.mention} (No role)"
            
            platforms_summary[platform].append(entry)
        
        for platform, entries in platforms_summary.items():
            platform_icon = "🎥" if platform == "youtube" else "🟣" if platform == "twitch" else "📱"
            embed.add_field(
                name=f"{platform_icon} {platform.title()} ({len(entries)})",
                value="\n\n".join(entries),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="check_creator", description="Manually check and post latest content from a creator")
    @app_commands.describe(
        creator="The creator's @handle or ID",
        platform="Platform the creator is on"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch")
    ])
    async def check_creator_command(self, interaction: discord.Interaction, creator: str, platform: str):
        """Manually check for latest content"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Get platform instance
        platform_instance = self.get_platform(platform)
        if not platform_instance:
            await interaction.followup.send(f"❌ Platform **{platform}** is not available.", ephemeral=True)
            return
        
        # Check if platform is configured
        if not platform_instance.is_configured(guild_id):
            await interaction.followup.send(f"❌ Platform **{platform}** is not configured.", ephemeral=True)
            return
        
        if platform == "youtube":
            creator_id = await platform_instance.get_channel_id(creator, guild_id)
            if not creator_id:
                await interaction.followup.send("❌ Couldn't find that YouTube channel.", ephemeral=True)
                return
            
            channel_info = await platform_instance.get_channel_info(creator_id, guild_id)
            if not channel_info:
                await interaction.followup.send("❌ Couldn't fetch channel information.", ephemeral=True)
                return
            
            channel_name = channel_info["snippet"]["title"]
            
            latest_video = await platform_instance.get_latest_content(creator_id, guild_id)
            if not latest_video:
                await interaction.followup.send(f"❌ No videos found for {channel_name}.", ephemeral=True)
                return
            
            video_id = latest_video["id"]["videoId"]
            video_url = f"https://youtube.com/watch?v={video_id}"
            description = await platform_instance.get_content_description(video_id, guild_id) or "No description available"
            
            if hasattr(platform_instance, 'clean_description'):
                description = platform_instance.clean_description(description)
            else:
                description = self.clean_description(description)
            
            if latest_video["snippet"].get("liveBroadcastContent") == "live":
                message = f"🎥 **{channel_name} is LIVE on YouTube!**\n\n{description}\n\n{video_url}"
            else:
                message = f"🎥 New video from **{channel_name} on YouTube!**\n\n{description}\n\n{video_url}"
            
            await interaction.channel.send(message)
            await interaction.followup.send(f"✅ Latest content from **{channel_name}** on YouTube posted!", ephemeral=True)
        
        elif platform == "twitch":
            # Get Twitch channel info
            creator_id = await platform_instance.get_channel_id(creator, guild_id)
            if not creator_id:
                await interaction.followup.send(f"❌ Couldn't find that Twitch channel.", ephemeral=True)
                return
            
            channel_info = await platform_instance.get_channel_info(creator_id, guild_id)
            if not channel_info:
                await interaction.followup.send(f"❌ Couldn't fetch Twitch channel information.", ephemeral=True)
                return
            
            stream_info = await platform_instance.get_latest_content(creator_id, guild_id)
            channel_name = channel_info["display_name"]
            
            if stream_info:
                # Channel is live
                stream_url = f"https://twitch.tv/{creator.lstrip('@')}"
                title = stream_info["title"]
                game_name = stream_info.get("game_name", "Unknown Game")
                viewer_count = stream_info.get("viewer_count", 0)
                
                message = f"🟣 **{channel_name} is LIVE on Twitch!**\n\n"
                message += f"**Playing:** {game_name}\n"
                message += f"**Title:** {title}\n"
                message += f"**Viewers:** {viewer_count}\n\n"
                message += stream_url
                
                await interaction.channel.send(message)
                await interaction.followup.send(f"✅ **{channel_name}** is currently live on Twitch!", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ **{channel_name}** is not currently streaming on Twitch.", ephemeral=True)
        
        else:
            await interaction.followup.send(f"❌ Platform **{platform}** manual check not implemented yet.", ephemeral=True)

async def setup(bot):
    cog = CreatorVideos(bot)
    await bot.add_cog(cog)
    return cog