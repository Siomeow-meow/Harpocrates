import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
from db import load_blob, save_blob

COLLECTION = "voice_channels"

# Discord rate-limits channel renames (~2 per 10 min per channel), so auto
# rename on presence changes needs a cooldown or it will silently 429.
RENAME_COOLDOWN_SECONDS = 300  # 5 minutes between auto-renames of the same channel


def get_activity_display(activities):
    """Return an (emoji, text) tuple describing the first meaningful activity,
    or (None, None) if there isn't one."""
    if not activities:
        return None, None

    for activity in activities:
        if isinstance(activity, discord.Spotify):
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
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.connect is False:
            await interaction.response.send_message("🔒 Channel is already locked!", ephemeral=True)
            return

        overwrite = discord.PermissionOverwrite()
        overwrite.connect = False
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔒 Channel locked - only you can join!", ephemeral=True)

    async def unlock_channel(self, interaction):
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.connect is not False:
            await interaction.response.send_message("🔓 Channel is already unlocked!", ephemeral=True)
            return

        overwrite = discord.PermissionOverwrite()
        overwrite.connect = True
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔓 Channel unlocked - anyone can join!", ephemeral=True)

    async def ghost_channel(self, interaction):
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.view_channel is False:
            await interaction.response.send_message("👻 Channel is already hidden!", ephemeral=True)
            return

        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = False
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("👻 Channel is now hidden from others!", ephemeral=True)

    async def unghost_channel(self, interaction):
        current_perms = self.channel.overwrites_for(interaction.guild.default_role)
        if current_perms.view_channel is not False:
            await interaction.response.send_message("👻 Channel is already visible!", ephemeral=True)
            return

        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = True
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("👻 Channel is now visible to everyone!", ephemeral=True)

    async def reject_user(self, interaction):
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
            user_input = self.username.value.strip()

            if user_input.isdigit():
                user = await interaction.client.fetch_user(int(user_input))
            else:
                user = None
                for member in interaction.guild.members:
                    if str(member) == user_input or member.name == user_input:
                        user = member
                        break

                if not user:
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

            if user in self.channel.members:
                default_channel = None
                for channel in interaction.guild.voice_channels:
                    if channel.id != self.channel.id:
                        default_channel = channel
                        break

                if default_channel:
                    await user.move_to(default_channel)
                else:
                    await user.move_to(None)

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
        self._last_rename = {}
        self.load_config()

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
        pass

    def load_config(self):
        """Load configuration from MongoDB.

        Shape per guild:
        {
            "creators": {channel_id (int): {"name": str, "editable": bool}},
            "order": [channel_id, ...]
        }
        No category_id is stored anymore because each creator channel can live
        in ANY category and temp channels spawn in that same category.
        """
        try:
            data = load_blob(COLLECTION)
            configs = {}
            for guild_id, config in data.items():
                creators = {int(cid): c for cid, c in config.get("creators", {}).items()}
                order = [int(cid) for cid in config.get("order", list(creators.keys()))]
                configs[int(guild_id)] = {
                    "creators": creators,
                    "order": order,
                }
            self.temp_channels_config = configs
            print(f"[INFO] Loaded voice channel config for {len(self.temp_channels_config)} guilds")
        except Exception as e:
            print(f"[ERROR] Failed to load config: {e}")
            self.temp_channels_config = {}

    def save_config(self):
        """Save configuration to MongoDB"""
        try:
            json_data = {}
            for guild_id, config in self.temp_channels_config.items():
                json_data[str(guild_id)] = {
                    "creators": {str(cid): c for cid, c in config.get("creators", {}).items()},
                    "order": [str(cid) for cid in config.get("order", [])],
                }
            success = save_blob(COLLECTION, json_data)
            if success:
                print(f"[INFO] Saved voice channel config for {len(self.temp_channels_config)} guilds")
            else:
                print("[ERROR] Failed to save config")
        except Exception as e:
            print(f"[ERROR] Failed to save config: {e}")

    async def find_existing_creator_channel(self, guild, name: str):
        """Look for an existing 'Join to Create' channel that matches the
        given name (case-insensitive, trimmed). Used so re-running /setup_vc
        with the same name doesn't create duplicates."""
        target = name.strip().lower()
        for channel in guild.voice_channels:
            if channel.name.strip().lower() == target:
                return channel
        return None

    @app_commands.command(name="setup_vc", description="Setup a temporary voice channel system")
    @app_commands.describe(
        name="Name for the 'Join to Create' voice channel",
        editable="Whether settings should be editable"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_voice(self, interaction: discord.Interaction, name: str = "➕ | Join To Create", editable: bool = True):
        name = name.strip()[:100]
        if not name:
            await interaction.response.send_message("❌ Channel name can't be empty.", ephemeral=True)
            return

        guild = interaction.guild
        config = self.temp_channels_config.setdefault(guild.id, {"creators": {}, "order": []})
        creators = config["creators"]

        # Don't create a duplicate creator channel with the same name.
        for cid, data in creators.items():
            existing = guild.get_channel(cid)
            if existing and data.get("name", "").lower() == name.lower():
                await interaction.response.send_message(
                    f"❌ A Join To Create channel named **{name}** already exists: {existing.mention}",
                    ephemeral=True
                )
                return

        # Auto-detect a pre-existing channel with that name and adopt it,
        # instead of creating a duplicate. This mirrors the JSON version's
        # "reuse if present" behavior.
        existing_channel = await self.find_existing_creator_channel(guild, name)
        if existing_channel:
            creators[existing_channel.id] = {"name": existing_channel.name, "editable": editable}
            config["order"].append(existing_channel.id)
            self.save_config()
            await interaction.response.send_message(
                f"✅ Using existing Join To Create channel: {existing_channel.mention}\n"
                "You can move this channel anywhere and it will still work.",
                ephemeral=True
            )
            return

        # Create a fresh creator channel. No forced category - it goes to
        # the top level, and admins can drag it into any category they like.
        vc = await guild.create_voice_channel(name)
        creators[vc.id] = {"name": name, "editable": editable}
        config["order"].append(vc.id)
        self.save_config()

        await interaction.response.send_message(
            "✅ Join To Create channel ready!\n"
            f"Channel: {vc.mention}\n"
            "You can move this channel anywhere (any category) and it will "
            "still work. Run `/setup_vc` again with a different name to add "
            "more creators.",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_ready(self):
        """Prune config entries whose Discord objects are gone. Never
        recreates or deletes anything - if you move or delete a channel
        yourself, it stays exactly how you left it."""
        print(f"[INFO] Bot is ready. Verifying {len(self.temp_channels_config)} guild configurations...")

        for guild_id, config in list(self.temp_channels_config.items()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"[WARNING] Guild {guild_id} not found, removing from config")
                del self.temp_channels_config[guild_id]
                continue

            creators = config.get("creators", {})
            for cid in list(creators.keys()):
                if not guild.get_channel(cid):
                    print(f"[INFO] Creator channel {cid} in guild {guild.name} no longer exists, untracking it")
                    del creators[cid]

            config["order"] = [cid for cid in config.get("order", []) if cid in creators]

            if not creators:
                del self.temp_channels_config[guild_id]
                continue

            print(f"[INFO] Verified {len(creators)} creator channel(s) for guild: {guild.name}")

        self.save_config()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild_config = self.temp_channels_config.get(member.guild.id)
        if not guild_config:
            return

        creators = guild_config.get("creators", {})

        # User joined one of this guild's creator channels
        if after.channel and after.channel.id in creators:
            try:
                member = await member.guild.fetch_member(member.id)
            except Exception:
                pass

            creator_channel = after.channel
            # Temp channel spawns in whatever category the creator channel is
            # currently in - no forced category.
            category = creator_channel.category

            channel_name = format_activity_channel_name(member.activities, f"{member.name}'s channel")

            temp_channel = await member.guild.create_voice_channel(
                channel_name,
                category=category,
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

        # Clean up empty temp channels
        channel_ids_to_check = list(self.temp_channels.keys())

        for channel_id in channel_ids_to_check:
            channel = member.guild.get_channel(channel_id)

            if not channel or len(channel.members) == 0:
                try:
                    data = self.temp_channels.get(channel_id)
                    if not data:
                        self.temp_channels.pop(channel_id, None)
                        continue

                    if "control_message_id" in data and channel:
                        try:
                            message = await channel.fetch_message(data["control_message_id"])
                            await message.delete()
                        except (discord.NotFound, discord.HTTPException):
                            pass

                    if channel:
                        await channel.delete()

                except discord.NotFound:
                    pass
                except Exception as e:
                    print(f"[ERROR] Failed to clean up channel {channel_id}: {e}")
                finally:
                    self.temp_channels.pop(channel_id, None)
                    self._last_rename.pop(channel_id, None)

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
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

        before_display = get_activity_display(before.activities)
        after_display = get_activity_display(after.activities)
        if before_display == after_display:
            return

        last = self._last_rename.get(channel_id, 0)
        if time.time() - last < RENAME_COOLDOWN_SECONDS:
            return

        new_name = format_activity_channel_name(after.activities, f"{after.name}'s channel")
        if new_name == channel.name:
            return

        try:
            await channel.edit(name=new_name)
            self._last_rename[channel_id] = time.time()
            print(f"[INFO] Auto-renamed channel {channel_id} to '{new_name}'")
        except discord.HTTPException as e:
            print(f"[ERROR] Auto-rename failed for channel {channel_id}: {e}")

    @app_commands.command(name="remove_vc", description="Remove the most recently created Join To Create channel")
    @app_commands.default_permissions(administrator=True)
    async def remove_voice(self, interaction: discord.Interaction):
        """Removes exactly one Join To Create channel per call, LIFO: the
        last one you created is the first one this removes."""
        config = self.temp_channels_config.get(interaction.guild.id)
        order = config.get("order", []) if config else []
        if not config or not order:
            await interaction.response.send_message(
                "❌ No temporary voice channel system is configured for this server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        creators = config.get("creators", {})
        cid = order.pop()
        creators.pop(cid, None)

        channel = interaction.guild.get_channel(cid)
        deleted_channel = False
        failed = False
        if channel:
            try:
                await channel.delete(reason="Removed via /remove_vc (LIFO)")
                deleted_channel = True
            except (discord.Forbidden, discord.HTTPException):
                failed = True

        if not order:
            del self.temp_channels_config[interaction.guild.id]
        else:
            config["creators"] = creators
            config["order"] = order

        self.save_config()

        if not deleted_channel:
            msg = "✅ Untracked it. It looks like it was already deleted on Discord." if not failed else \
                  "⚠️ Untracked it, but I don't have permission to delete it on Discord."
            await interaction.followup.send(msg, ephemeral=True)
            return

        remaining = len(order)
        summary = "✅ Removed its Join To Create channel."
        if remaining:
            summary += f" {remaining} other Join To Create channel(s) still remain."
        await interaction.followup.send(summary, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Voice(bot))