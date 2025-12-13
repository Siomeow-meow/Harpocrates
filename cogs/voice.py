import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os

VOICE_CHANNELS_FILE = "data/voice_channels.json"

class ChannelSettings(discord.ui.Select):
    def __init__(self, channel, member):
        options = [
            discord.SelectOption(label="Name", description="Change the channel name"),
            discord.SelectOption(label="Status", description="Change the channel status"),
            discord.SelectOption(label="User Limit", description="Change the user limit"),
            discord.SelectOption(label="Gaming", description="Set name based on your activity")
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
        elif self.values[0] == "Gaming":
            await self.set_gaming_name(interaction)
        
        await interaction.followup.edit_message(interaction.message.id, view=ControlView(self.channel, self.member))
    
    async def set_gaming_name(self, interaction: discord.Interaction):
        try:
            # Refresh member data to get current activities
            try:
                member = await interaction.guild.fetch_member(self.member.id)
            except:
                member = self.member  # Fallback to original member if fetch fails
            
            activities = member.activities
            if not activities:
                await interaction.response.send_message(
                    "❌ No activities detected. Make sure:\n"
                    "1. Your game/activity is running\n"
                    "2. Discord overlay is enabled for the game\n"
                    "3. Your activity status is visible in Discord",
                    ephemeral=True
                )
                return
            
            print(f"[DEBUG] Activities for {member}: {[(a.type, a.name) for a in activities]}")  # Debug output
            
            game_name = None
            for activity in activities:
                # Check all possible activity types
                if isinstance(activity, discord.Game):
                    game_name = activity.name
                    break
                elif activity.type == discord.ActivityType.playing:
                    game_name = activity.name
                    break
                elif activity.type == discord.ActivityType.streaming:
                    game_name = f"Streaming {activity.name}"
                    break
                elif activity.type == discord.ActivityType.listening:
                    if isinstance(activity, discord.Spotify):
                        game_name = f"Listening to {activity.title}"
                    else:
                        game_name = f"Listening to {activity.name}"
                    break
                elif activity.type == discord.ActivityType.watching:
                    game_name = f"Watching {activity.name}"
                    break
                elif activity.type == discord.ActivityType.custom:
                    if activity.name:
                        game_name = activity.name
                        break
            
            if game_name:
                new_name = f"🎮 {game_name}"[:32]  # Ensure name is within Discord's 32 character limit
                try:
                    await self.channel.edit(name=new_name)
                    await interaction.response.send_message(
                        f"✅ Channel renamed to: {new_name}",
                        ephemeral=True
                    )
                except discord.HTTPException as e:
                    await interaction.response.send_message(
                        f"❌ Couldn't rename channel: {str(e)}",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    "❌ No game activity detected. Try:\n"
                    "1. Restart your game with Discord overlay enabled\n"
                    "2. Update your Discord status manually\n"
                    "3. Check your Discord activity settings",
                    ephemeral=True
                )
        except Exception as e:
            print(f"[ERROR] in set_gaming_name: {str(e)}")
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
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

class ChannelStatusModal(discord.ui.Modal, title="Change Channel Status"):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.new_status = discord.ui.TextInput(
            label="New Status",
            placeholder="Enter new status...",
            max_length=100
        )
        self.add_item(self.new_status)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"✅ Status updated to: {self.new_status.value}", ephemeral=True)

class ChannelLimitModal(discord.ui.Modal, title="Change User Limit"):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.new_limit = discord.ui.TextInput(
            label="User Limit",
            placeholder="(0 for unlimited)",
            max_length=2
        )
        self.add_item(self.new_limit)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.new_limit.value)
            await self.channel.edit(user_limit=limit)
            await interaction.response.send_message(f"✅ User limit set to {limit}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number", ephemeral=True)

class PermissionSettings(discord.ui.Select):
    def __init__(self, channel, creator):
        options = [
            discord.SelectOption(label="Lock", description="Lock the channel"),
            discord.SelectOption(label="Unlock", description="Unlock the channel"),
            discord.SelectOption(label="Permit", description="Allow a user to join"),
            discord.SelectOption(label="Reject", description="Kick a user from channel"),
            discord.SelectOption(label="Ghost", description="Make your channel invisible"),
            discord.SelectOption(label="Unghost", description="Make your channel visible")
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
        elif self.values[0] == "Permit":
            await self.permit_user(interaction)
        elif self.values[0] == "Reject":
            await self.reject_user(interaction)
        elif self.values[0] == "Ghost":
            await self.ghost_channel(interaction)
        elif self.values[0] == "Unghost":
            await self.unghost_channel(interaction)
        
        await interaction.followup.edit_message(interaction.message.id, view=ControlView(self.channel, interaction.user))
    
    async def lock_channel(self, interaction):
        overwrite = discord.PermissionOverwrite()
        overwrite.connect = False
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔒 Channel locked", ephemeral=True)
    
    async def unlock_channel(self, interaction):
        overwrite = discord.PermissionOverwrite()
        overwrite.connect = True
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)
    
    async def ghost_channel(self, interaction):
        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = False
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("👻 Channel is now hidden", ephemeral=True)
    
    async def unghost_channel(self, interaction):
        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = True
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("👻 Channel is now visible", ephemeral=True)
    
    async def permit_user(self, interaction):
        await interaction.response.send_message("⚠️ Feature not yet implemented", ephemeral=True)
    
    async def reject_user(self, interaction):
        await interaction.response.send_message("⚠️ Feature not yet implemented", ephemeral=True)

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
        self.load_config()

    def load_config(self):
        """Load configuration from JSON file"""
        try:
            # Create data directory if it doesn't exist
            os.makedirs(os.path.dirname(VOICE_CHANNELS_FILE), exist_ok=True)
            
            if os.path.exists(VOICE_CHANNELS_FILE):
                with open(VOICE_CHANNELS_FILE, 'r') as f:
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
            
            with open(VOICE_CHANNELS_FILE, 'w') as f:
                json.dump(self.temp_channels_config, f, indent=4)
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
    @app_commands.describe(editable="Whether settings should be editable")
    @app_commands.default_permissions(administrator=True)
    async def setup_voice(self, interaction: discord.Interaction, editable: bool = True):
        existing_channel = await self.find_existing_creator_channel(interaction.guild)
        
        if existing_channel:
            category = existing_channel.category
            if not category:
                category = await interaction.guild.create_category("Temporary Channels")
                await existing_channel.edit(category=category)
            
            self.temp_channels_config[interaction.guild.id] = {
                "editable": editable,
                "category_id": category.id,
                "creator_channel_id": existing_channel.id
            }
            self.save_config()  # Save to file
            
            await interaction.response.send_message(
                f"✅ Using existing Join To Create channel: {existing_channel.mention}\n"
                "You can move this channel anywhere and it will still work.",
                ephemeral=True
            )
            return

        category = await interaction.guild.create_category("Temporary Channels")
        vc = await category.create_voice_channel("➕ | Join to Create")
        
        self.temp_channels_config[interaction.guild.id] = {
            "editable": editable,
            "category_id": category.id,
            "creator_channel_id": vc.id
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
            
            # Check if creator channel exists
            creator_channel = guild.get_channel(config.get("creator_channel_id"))
            if not creator_channel:
                print(f"[WARNING] Creator channel not found in guild {guild.name}, removing config")
                del self.temp_channels_config[guild_id]
                continue
            
            # Check if category exists
            category = guild.get_channel(config.get("category_id"))
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
            channel_name = f"{member.name}'s channel"
            if member.activities:
                for activity in member.activities:
                    if isinstance(activity, discord.Game) or activity.type in [
                        discord.ActivityType.playing,
                        discord.ActivityType.streaming
                    ]:
                        channel_name = f"🎮 {activity.name}"[:32]
                        break
            
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
                value="• Lock/unlock\n• Permit users\n• Reject users",
                inline=True
            )
            
            view = ControlView(temp_channel, member)
            
            try:
                message = await temp_channel.send(embed=embed, view=view)
                self.temp_channels[temp_channel.id] = {
                    "control_message_id": message.id,
                    "creator_id": member.id,
                    "guild_id": member.guild.id
                }
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