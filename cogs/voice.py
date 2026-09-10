import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
import time

VOICE_CHANNELS_FILE = "data/voice_channels.json"

# Discord rate-limits channel renames (~2 per 10 min per channel), so auto
# rename on presence changes needs a cooldown or it will silently 429.
RENAME_COOLDOWN_SECONDS = 300  # 5 minutes between auto-renames of the same channel


def get_activity_display(activities):
    """Return an (emoji, text) tuple describing the first meaningful activity,
    or (None, None) if there isn't one.

    IMPORTANT: activities are only populated via the gateway PRESENCE_UPDATE
    event, which requires Intents.presences (and the "Presence Intent" toggle
    enabled in the Discord Developer Portal for the bot). REST calls like
    guild.fetch_member() never include activity/presence data, no matter how
    "fresh" the fetch is - so don't rely on fetch_member() to get activities.
    """
    if not activities:
        return None, None

    for activity in activities:
        if isinstance(activity, discord.Spotify):
            # Spotify activities are always "listening" type but carry richer
            # metadata (title + artist) than a generic listening activity.
            artist = activity.artists[0] if getattr(activity, "artists", None) else None
            text = f"{activity.title} - {artist}" if artist else activity.title
            return "🎵", text
        elif isinstance(activity, discord.Game):
            return "🎮", activity.name
        elif activity.type == discord.ActivityType.playing:
            return "🎮", activity.name
        elif activity.type == discord.ActivityType.streaming:
            return "🔴", activity.name
        elif activity.type == discord.ActivityType.listening:
            return "🎧", activity.name
        elif activity.type == discord.ActivityType.watching:
            return "📺", activity.name
        elif activity.type == discord.ActivityType.competing:
            return "🏆", activity.name
        elif activity.type == discord.ActivityType.custom:
            if activity.name:
                return "💬", activity.name
    return None, None


def format_activity_channel_name(activities, fallback: str) -> str:
    """Build a Discord-safe (<=32 char) channel name from a member's activity,
    falling back to `fallback` (e.g. "<name>'s channel") if there's none."""
    emoji, text = get_activity_display(activities)
    if not text:
        return fallback[:32]
    return f"{emoji} {text}"[:32]

class ChannelSettings(discord.ui.Select):
    def __init__(self, channel, member):
        options = [
            discord.SelectOption(label="Name", description="Change the channel name"),
            discord.SelectOption(label="Status", description="Change the channel status"),
            discord.SelectOption(label="User Limit", description="Change the user limit"),
            discord.SelectOption(label="Auto Status", description="Toggle auto-renaming as your activity changes")
        ]
        super().__init__(placeholder="Change channel settings...", options=options)
        self.channel = channel
        self.member = member
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "Name":
            modal = ChannelNameModal(self.channel)
            await interaction.response.send_modal(modal)
        elif self.values[0] == "Status":
            modal = ChannelStatusModal(self.channel)
            await interaction.response.send_modal(modal)
        elif self.values[0] == "User Limit":
            modal = ChannelLimitModal(self.channel)
            await interaction.response.send_modal(modal)
        elif self.values[0] == "Auto Status":
            await self.toggle_auto_status(interaction)
        
        await interaction.followup.edit_message(interaction.message.id, view=ControlView(self.channel, self.member))

    async def toggle_auto_status(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Voice")
        data = cog.temp_channels.get(self.channel.id) if cog else None
        if data is None:
            await interaction.response.send_message(
                "❌ Couldn't find this channel's settings.", ephemeral=True
            )
            return
        data["auto_status"] = not data.get("auto_status", False)
        if cog:
            cog.save_temp_channels()
        state = "enabled ✅" if data["auto_status"] else "disabled ❌"
        await interaction.response.send_message(
            f"Auto status is now **{state}**. When enabled, the channel name "
            "updates automatically (at most once every 5 minutes) as your "
            "activity changes.",
            ephemeral=True
        )

class ChannelNameModal(discord.ui.Modal, title="Change Channel Name"):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.new_name = discord.ui.TextInput(
            label="New Channel Name",
            placeholder="Enter new name...",
            max_length=100
        )
        self.add_item(self.new_name)
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.channel.edit(name=self.new_name.value)
        await interaction.response.send_message(f"✅ Channel renamed to {self.new_name.value}", ephemeral=True)

class ChannelStatusModal(discord.ui.Modal, title="Set Channel Status"):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.new_status = discord.ui.TextInput(
            label="Status",
            placeholder="What are you up to?",
            style=discord.TextStyle.short,
            max_length=100,
            required=False
        )
        self.add_item(self.new_status)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            status_text = self.new_status.value.strip() if self.new_status.value else None
            await self.channel.edit(status=status_text)
            
            if status_text:
                await interaction.response.send_message(
                    f"✅ Channel status set to:\n*{status_text}*",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "✅ Channel status has been cleared!",
                    ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to change the channel status!",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to update status: {str(e)}",
                ephemeral=True
            )

class ChannelLimitModal(discord.ui.Modal, title="Change User Limit"):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.new_limit = discord.ui.TextInput(
            label="User Limit",
            placeholder="0 for unlimited, or 1-99 for a limit",
            max_length=2,
            min_length=1
        )
        self.add_item(self.new_limit)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.new_limit.value)
            if 0 <= limit <= 99:
                await self.channel.edit(user_limit=limit)
                if limit == 0:
                    await interaction.response.send_message(
                        "✅ User limit set to **unlimited** (0)",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"✅ User limit set to **{limit}**",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    "❌ Please enter a number between **0** (unlimited) and **99**",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number",
                ephemeral=True
            )

class PermissionSettings(discord.ui.Select):
    def __init__(self, channel, creator):
        options = [
            discord.SelectOption(label="Lock", description="Make channel private (only you can join)"),
            discord.SelectOption(label="Unlock", description="Make channel public (anyone can join)"),
            discord.SelectOption(label="Reject", description="Kick a user from your channel"),
            discord.SelectOption(label="Ghost", description="Make your channel invisible to others"),
            discord.SelectOption(label="Unghost", description="Make your channel visible to others")
        ]
        super().__init__(placeholder="Change permission settings...", options=options)
        self.channel = channel
        self.creator = creator
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.creator:
            await interaction.response.send_message("❌ Only the channel creator can modify permissions", ephemeral=True)
            return
            
        if self.values[0] == "Lock":
            await self.lock_channel(interaction)
        elif self.values[0] == "Unlock":
            await self.unlock_channel(interaction)
        elif self.values[0] == "Reject":
            await self.reject_user(interaction)
        elif self.values[0] == "Ghost":
            await self.ghost_channel(interaction)
        elif self.values[0] == "Unghost":
            await self.unghost_channel(interaction)
        
        await interaction.followup.edit_message(interaction.message.id, view=ControlView(self.channel, interaction.user))
    
    async def lock_channel(self, interaction):
        # Check if channel is already locked
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.connect is False:
            await interaction.response.send_message("🔒 Channel is already locked!", ephemeral=True)
            return
        
        overwrite = discord.PermissionOverwrite()
        overwrite.connect = False
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔒 Channel locked - only you can join!", ephemeral=True)
    
    async def unlock_channel(self, interaction):
        # Check if channel is already unlocked
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.connect is not False:
            await interaction.response.send_message("🔓 Channel is already unlocked!", ephemeral=True)
            return
        
        overwrite = discord.PermissionOverwrite()
        overwrite.connect = True
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔓 Channel unlocked - anyone can join!", ephemeral=True)
    
    async def ghost_channel(self, interaction):
        # Check if channel is already ghosted
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.view_channel is False:
            await interaction.response.send_message("👻 Channel is already hidden!", ephemeral=True)
            return
        
        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = False
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("👻 Channel is now hidden from others!", ephemeral=True)
    
    async def unghost_channel(self, interaction):
        # Check if channel is already visible
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.view_channel is not False:
            await interaction.response.send_message("👻 Channel is already visible!", ephemeral=True)
            return
        
        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = True
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("👻 Channel is now visible to everyone!", ephemeral=True)
    
    async def reject_user(self, interaction):
        # Show a modal to enter username
        modal = RejectUserModal(self.channel, interaction.user)
        await interaction.response.send_modal(modal)

class RejectUserModal(discord.ui.Modal, title="Reject User"):
    def __init__(self, channel, creator):
        super().__init__()
        self.channel = channel
        self.creator = creator
        self.username = discord.ui.TextInput(
            label="Username or User ID",
            placeholder="Enter username#tag or user ID",
            max_length=100
        )
        self.add_item(self.username)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Try to find the user
            user_input = self.username.value.strip()
            
            # Try to get by ID first
            if user_input.isdigit():
                user = await interaction.client.fetch_user(int(user_input))
            else:
                # Search by name
                user = None
                for member in interaction.guild.members:
                    if str(member) == user_input or member.name == user_input:
                        user = member
                        break
                
                if not user:
                    # Try to find by nickname
                    for member in interaction.guild.members:
                        if member.nick == user_input:
                            user = member
                            break
            
            if not user:
                await interaction.response.send_message(
                    f"❌ Could not find user '{self.username.value}'. Please use username#tag or user ID.",
                    ephemeral=True
                )
                return
            
            # Kick the user from the channel if they're in it
            if user in self.channel.members:
                # Find a different voice channel to move them to
                default_channel = None
                for channel in interaction.guild.voice_channels:
                    if channel.id != self.channel.id:
                        default_channel = channel
                        break
                
                if default_channel:
                    await user.move_to(default_channel)
                else:
                    await user.move_to(None)  # Disconnect them
            
            # Remove their permissions to reconnect
            overwrite = discord.PermissionOverwrite()
            overwrite.connect = False
            await self.channel.set_permissions(user, overwrite=overwrite)
            
            await interaction.response.send_message(
                f"✅ {user.mention} has been rejected from your channel!",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

class ControlView(discord.ui.View):
    def __init__(self, channel, creator):
        super().__init__(timeout=None)
        self.add_item(ChannelSettings(channel, creator))
        self.add_item(PermissionSettings(channel, creator))

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_channels_config = {}
        self.temp_channels = {}
        self._last_rename = {}  # channel_id -> timestamp of last auto-rename
        self.load_config()

        # Presence Intent sanity check - without this, activities are always empty.
        if not bot.intents.presences:
            print(
                "[WARNING] Intents.presences is not enabled. Auto Status "
                "features will never detect activities. Enable it via "
                "intents.presences = True in your bot setup AND in the "
                "Discord Developer Portal under Bot > Privileged Gateway Intents."
            )
        if not bot.intents.members:
            print(
                "[WARNING] Intents.members is not enabled. Member caching for "
                "voice channel features may be unreliable."
            )

    def save_temp_channels(self):
        """Persist per-channel runtime state (e.g. auto_status toggle)."""
        # Kept in-memory only by default since temp channels don't survive a
        # restart anyway; hook here if you want to persist across restarts.
        pass

    def load_config(self):
        """Load configuration from JSON file"""
        try:
            # Create data directory if it doesn't exist
            os.makedirs(os.path.dirname(VOICE_CHANNELS_FILE), exist_ok=True)
            
            if os.path.exists(VOICE_CHANNELS_FILE):
                with open(VOICE_CHANNELS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.temp_channels_config = {int(k): v for k, v in data.items()}
                    print(f"[INFO] Loaded voice channel config for {len(self.temp_channels_config)} guilds")
            else:
                print(f"[INFO] No config file found at {VOICE_CHANNELS_FILE}")
        except Exception as e:
            print(f"[ERROR] Failed to load config: {e}")
            self.temp_channels_config = {}

    def save_config(self):
        """Save configuration to JSON file"""
        try:
            # Create data directory if it doesn't exist
            os.makedirs(os.path.dirname(VOICE_CHANNELS_FILE), exist_ok=True)
            
            with open(VOICE_CHANNELS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.temp_channels_config, f, indent=4, ensure_ascii=False)
            print(f"[INFO] Saved voice channel config for {len(self.temp_channels_config)} guilds")
        except Exception as e:
            print(f"[ERROR] Failed to save config: {e}")

    async def find_existing_creator_channel(self, guild):
        """Check if a Join To Create channel already exists in the guild"""
        for channel in guild.voice_channels:
            if channel.name.lower().startswith(("➕", "+")) and "join to create" in channel.name.lower():
                return channel
        return None

    @app_commands.command(name="setup_vc", description="Setup the temporary voice channel system")
    @app_commands.describe(
        name="Name for the 'Join to Create' voice channel",
        editable="Whether settings should be editable"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_voice(self, interaction: discord.Interaction, name: str, editable: bool = True):
        name = name.strip()[:100]
        if not name:
            await interaction.response.send_message("❌ Channel name can't be empty.", ephemeral=True)
            return

        # Only auto-detect a pre-existing creator channel when the caller
        # didn't ask for a specific custom name - otherwise honor the name
        # they gave and create a fresh channel for it.
        existing_channel = None
        if name == "➕ | Join to Create":
            existing_channel = await self.find_existing_creator_channel(interaction.guild)

        if existing_channel:
            category = existing_channel.category
            if not category:
                category = await interaction.guild.create_category("Temporary Channels")
                await existing_channel.edit(category=category)
            
            self.temp_channels_config[interaction.guild.id] = {
                "editable": editable,
                "category_id": category.id,
                "creator_channel_id": existing_channel.id,
                "creator_channel_name": existing_channel.name
            }
            self.save_config()  # Save to file
            
            await interaction.response.send_message(
                f"✅ Using existing Join To Create channel: {existing_channel.mention}\n"
                "You can move this channel anywhere and it will still work.",
                ephemeral=True
            )
            return

        category = await interaction.guild.create_category("Temporary Channels")
        vc = await category.create_voice_channel(name)
        
        self.temp_channels_config[interaction.guild.id] = {
            "editable": editable,
            "category_id": category.id,
            "creator_channel_id": vc.id,
            "creator_channel_name": name
        }
        self.save_config()  # Save to file
        
        await interaction.response.send_message(
            "✅ Temporary channel system setup complete!\n"
            f"Join To Create channel: {vc.mention}\n"
            "You can move this channel anywhere and it will still work.",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_ready(self):
        """Verify all configured channels still exist when bot starts"""
        print(f"[INFO] Bot is ready. Verifying {len(self.temp_channels_config)} guild configurations...")
        
        for guild_id, config in list(self.temp_channels_config.items()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"[WARNING] Guild {guild_id} not found, removing from config")
                del self.temp_channels_config[guild_id]
                continue
            
            # Check if creator channel exists - recreate it using the saved
            # name/category instead of dropping the whole config if it's gone
            creator_channel = guild.get_channel(config.get("creator_channel_id"))
            category = guild.get_channel(config.get("category_id"))

            if not creator_channel:
                try:
                    if not category:
                        category = await guild.create_category("Temporary Channels")
                        config["category_id"] = category.id
                    creator_name = config.get("creator_channel_name", "➕ | Join to Create")
                    creator_channel = await category.create_voice_channel(creator_name)
                    config["creator_channel_id"] = creator_channel.id
                    print(f"[INFO] Recreated missing creator channel for guild {guild.name}")
                except Exception as e:
                    print(f"[ERROR] Failed to recreate creator channel for guild {guild.name}: {e}")
                    del self.temp_channels_config[guild_id]
                    continue
            
            # Check if category exists
            if not category:
                # Create new category if missing
                try:
                    category = await guild.create_category("Temporary Channels")
                    await creator_channel.edit(category=category)
                    config["category_id"] = category.id
                    print(f"[INFO] Recreated category for guild {guild.name}")
                except Exception as e:
                    print(f"[ERROR] Failed to recreate category for guild {guild.name}: {e}")
                    del self.temp_channels_config[guild_id]
                    continue
            
            print(f"[INFO] Verified configuration for guild: {guild.name}")
        
        # Save any updates to config
        if self.temp_channels_config:
            self.save_config()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild_config = self.temp_channels_config.get(member.guild.id)
        if not guild_config:
            return
        
        # User joined the creator channel
        if after.channel and after.channel.id == guild_config["creator_channel_id"]:
            try:
                # Refresh member data to get current activities
                member = await member.guild.fetch_member(member.id)
            except:
                pass  # Use original member if refresh fails
            
            creator_channel = after.channel
            category = creator_channel.category
            
            if not category:
                category = await member.guild.create_category("Temporary Channels")
                await creator_channel.edit(category=category)
                guild_config["category_id"] = category.id
                self.save_config()
            
            # Set initial channel name based on activity
            channel_name = format_activity_channel_name(member.activities, f"{member.name}'s channel")
            
            temp_channel = await category.create_voice_channel(
                channel_name,
                user_limit=0
            )
            
            await member.move_to(temp_channel)
            
            embed = discord.Embed(
                title="Temporary Voice Channel Controls",
                description="Use the dropdown menus below to manage your channel.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Channel Settings",
                value="• Change name\n• Set status\n• User limit\n• Auto-name by activity",
                inline=True
            )
            embed.add_field(
                name="Permissions",
                value="• Lock/unlock\n• Reject users\n• Ghost/Unghost",
                inline=True
            )
            
            view = ControlView(temp_channel, member)
            
            try:
                message = await temp_channel.send(embed=embed, view=view)
                self.temp_channels[temp_channel.id] = {
                    "control_message_id": message.id,
                    "creator_id": member.id,
                    "guild_id": member.guild.id,
                    "auto_status": False
                }
                self._last_rename[temp_channel.id] = time.time()
            except Exception as e:
                print(f"[ERROR] Failed to send control message: {e}")
        
        # Clean up empty channels - FIXED VERSION with safe deletion
        channel_ids_to_check = list(self.temp_channels.keys())
        
        for channel_id in channel_ids_to_check:
            channel = member.guild.get_channel(channel_id)
            
            # If channel doesn't exist or is empty
            if not channel or len(channel.members) == 0:
                try:
                    # Get data before potentially removing from dictionary
                    data = self.temp_channels.get(channel_id)
                    if not data:
                        # If no data, just remove the key and continue
                        self.temp_channels.pop(channel_id, None)
                        continue
                    
                    # Try to delete the control message if channel exists
                    if "control_message_id" in data and channel:
                        try:
                            message = await channel.fetch_message(data["control_message_id"])
                            await message.delete()
                        except (discord.NotFound, discord.HTTPException):
                            pass  # Message might already be deleted
                    
                    # Delete the channel if it exists
                    if channel:
                        await channel.delete()
                    
                except discord.NotFound:
                    # Channel already deleted
                    pass
                except Exception as e:
                    print(f"[ERROR] Failed to clean up channel {channel_id}: {e}")
                finally:
                    # Always remove from dictionary safely
                    self.temp_channels.pop(channel_id, None)
                    self._last_rename.pop(channel_id, None)

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Auto-rename a temp channel when its creator's activity changes,
        if that creator has Auto Status enabled - subject to a cooldown to
        stay under Discord's channel-rename rate limit."""
        # Find a temp channel this member owns and currently sits in
        entry = None
        channel_id = None
        for cid, data in self.temp_channels.items():
            if data.get("creator_id") == after.id and data.get("guild_id") == after.guild.id:
                channel_id, entry = cid, data
                break

        if not entry or not entry.get("auto_status"):
            return

        channel = after.guild.get_channel(channel_id)
        if not channel or after not in channel.members:
            return

        # Only bother if activities actually changed
        before_display = get_activity_display(before.activities)
        after_display = get_activity_display(after.activities)
        if before_display == after_display:
            return

        last = self._last_rename.get(channel_id, 0)
        if time.time() - last < RENAME_COOLDOWN_SECONDS:
            return  # cooldown active, skip to avoid rate limiting

        new_name = format_activity_channel_name(after.activities, f"{after.name}'s channel")
        if new_name == channel.name:
            return

        try:
            await channel.edit(name=new_name)
            self._last_rename[channel_id] = time.time()
            print(f"[INFO] Auto-renamed channel {channel_id} to '{new_name}'")
        except discord.HTTPException as e:
            print(f"[ERROR] Auto-rename failed for channel {channel_id}: {e}")

    @app_commands.command(name="remove_vc", description="Remove the temporary voice channel system")
    @app_commands.default_permissions(administrator=True)
    async def remove_voice(self, interaction: discord.Interaction):
        """Command to remove the VC system from a guild"""
        if interaction.guild.id in self.temp_channels_config:
            del self.temp_channels_config[interaction.guild.id]
            self.save_config()
            await interaction.response.send_message(
                "✅ Temporary voice channel system removed.\n"
                "Note: Existing Join To Create channels won't be deleted automatically.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ No temporary voice channel system is configured for this server.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Voice(bot))