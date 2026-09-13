import discord
from discord.ext import commands, tasks
from discord import app_commands
import re
import time
from datetime import datetime, timedelta
import asyncio
from db import load_blob, save_blob

COLLECTION = "tracked_channels"
CACHE_DURATION = 15 * 60

class CreatorVideos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.platforms = {}
        self.cache = {}
        self.tracked_channels = self.load_tracked_channels()


        self.initialized = False

        self.check_uploads.start()

    def load_tracked_channels(self):
        try:
            data = load_blob(COLLECTION)
            if not data:
                print("⚠️ No tracked channels found in MongoDB, starting fresh")
            return data
        except Exception as e:
            print(f"❌ Error loading tracked channels from MongoDB: {e}")
            return {}

    def save_tracked_channels(self):
        try:
            success = save_blob(COLLECTION, self.tracked_channels)
            if not success:
                print("❌ Error saving tracked channels")
            return success
        except Exception as e:
            print(f"❌ Error saving tracked channels: {e}")
            return False

    def register_platform(self, platform_name, platform_instance):
        self.platforms[platform_name.lower()] = platform_instance
        print(f"✅ Registered platform: {platform_name}")

    def get_platform(self, platform_name):
        return self.platforms.get(platform_name.lower())

    def cog_unload(self):
        self.check_uploads.cancel()

    async def restore_roles_on_startup(self):
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
        if not description:
            return ""
        return re.sub(r'(https?://\S+)', lambda m: f'<{m.group(1)}>', description)

    def is_cache_valid(self, cache_timestamp):
        if not cache_timestamp:
            return False
        return (time.time() - cache_timestamp) < CACHE_DURATION

    @tasks.loop(minutes=30)
    async def check_uploads(self):
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

                        if "last_content_id" in data:
                            self.tracked_channels[creator_key]["last_content_id"] = None
                            self.save_tracked_channels()


            except Exception as e:
                print(f"Error checking {platform_name} creator {creator_key}: {e}")

    @check_uploads.before_loop
    async def before_check_uploads(self):
        await self.bot.wait_until_ready()

        await self.restore_roles_on_startup()


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


    def configured_platform_options(self, guild_id: int):
        options = []
        if self.bot.youtube_platform and self.bot.youtube_platform.is_configured(guild_id):
            options.append(discord.SelectOption(label="YouTube", value="youtube", emoji="🎥"))
        if self.bot.twitch_platform and self.bot.twitch_platform.is_configured(guild_id):
            options.append(discord.SelectOption(label="Twitch", value="twitch", emoji="🟣"))
        return options

    def build_creators_embed(self, guild: discord.Guild) -> discord.Embed:
        guild_tracked = {k: v for k, v in self.tracked_channels.items()
                          if v.get("guild_id") == guild.id}

        embed = discord.Embed(title="📺 Tracked Content Creators", color=0x5865F2)

        if not guild_tracked:
            embed.description = "No content creators are currently being tracked."
            return embed

        platforms_summary = {}
        for creator_key, data in guild_tracked.items():
            platform = data.get("platform", "Unknown")
            platforms_summary.setdefault(platform, [])

            channel_name = data.get("creator_name", "Unknown Creator")
            handle = data.get("creator_input", "").strip()
            discord_channel = self.bot.get_channel(data["discord_channel_id"])
            user = guild.get_member(data.get("user_id", 0))
            role = guild.get_role(data.get("role_id", 0))

            entry = f"**{channel_name}**"
            if handle:
                entry += f"\n↳ Handle: `{handle}`"
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
                inline=False,
            )

        return embed

    async def find_creator_key(self, guild_id: int, platform: str, creator: str, channel_id: int = None):
        for key, data in self.tracked_channels.items():
            if (data.get("platform") == platform
                    and data.get("creator_input", "").lower() == creator.lower()
                    and data.get("guild_id") == guild_id
                    and (channel_id is None or data.get("discord_channel_id") == channel_id)):
                return key
        return None


    async def do_follow(self, interaction: discord.Interaction, creator: str, platform: str,
                         target_channel: discord.TextChannel, user: discord.Member = None,
                         role: discord.Role = None):
        guild_id = interaction.guild.id

        platform_instance = self.get_platform(platform)
        if not platform_instance:
            await interaction.followup.send(f"❌ Platform **{platform}** is not available.", ephemeral=True)
            return

        if not platform_instance.is_configured(guild_id):
            await interaction.followup.send(
                f"❌ Platform **{platform}** is not configured for this server.\n"
                f"Use `/platforms` first to configure the API.",
                ephemeral=True,
            )
            return

        creator_id = await platform_instance.get_channel_id(creator, guild_id)
        if not creator_id:
            await interaction.followup.send(f"❌ Couldn't find that {platform.title()} channel.", ephemeral=True)
            return

        channel_info = await platform_instance.get_channel_info(creator_id, guild_id)
        if not channel_info:
            await interaction.followup.send(f"❌ Couldn't fetch {platform.title()} channel information.", ephemeral=True)
            return

        if platform == "youtube":
            creator_name = channel_info["snippet"]["title"]
            platform_icon = "🎥"
        elif platform == "twitch":
            creator_name = channel_info["display_name"]
            platform_icon = "🟣"
        else:
            creator_name = creator
            platform_icon = "📱"

        if not target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.followup.send(f"❌ No permission to send messages in {target_channel.mention}", ephemeral=True)
            return

        if (user and not role) or (role and not user):
            await interaction.followup.send("❌ Please provide both user and role, or neither.", ephemeral=True)
            return

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

        creator_key = f"{platform}_{creator_id}"
        if creator_key in self.tracked_channels:
            existing_data = self.tracked_channels[creator_key]
            if existing_data.get("guild_id") == guild_id:
                existing_channel = self.bot.get_channel(existing_data["discord_channel_id"])
                existing_user = interaction.guild.get_member(existing_data.get("user_id", 0))
                user_mention = existing_user.mention if existing_user else "another user"
                channel_mention = existing_channel.mention if existing_channel else "another channel"
                await interaction.followup.send(
                    f"❌ **{creator_name}** is already being tracked by {user_mention} in {channel_mention}.",
                    ephemeral=True,
                )
                return

        last_content_id = None
        latest_content = await platform_instance.get_latest_content(creator_id, guild_id)
        if latest_content:
            if platform == "youtube":
                last_content_id = latest_content["id"]["videoId"]
            elif platform == "twitch":
                last_content_id = latest_content.get("id")

        tracking_data = {
            "platform": platform,
            "guild_id": guild_id,
            "discord_channel_id": target_channel.id,
            "last_content_id": last_content_id,
            "creator_name": creator_name,
            "creator_input": creator,
            "creator_id": creator_id,
        }

        if user and role:
            tracking_data["user_id"] = user.id
            tracking_data["role_id"] = role.id

        self.tracked_channels[creator_key] = tracking_data

        if self.save_tracked_channels():
            print(f"✅ Successfully saved tracked creator: {creator_name}")
        else:
            print(f"❌ Failed to save tracked creator: {creator_name}")

        if user and role:
            try:
                await user.add_roles(role)
                success_message = (
                    f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** "
                    f"in {target_channel.mention} and assigned {role.mention} to {user.mention}!"
                )
            except discord.Forbidden:
                success_message = (
                    f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** "
                    f"in {target_channel.mention}, but couldn't assign role due to permissions."
                )
            except Exception as e:
                success_message = (
                    f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** "
                    f"in {target_channel.mention}, but error assigning role: {e}"
                )
        else:
            success_message = (
                f"✅ Now tracking **{creator_name}** on {platform_icon} **{platform.title()}** "
                f"in {target_channel.mention}!"
            )

        await interaction.followup.send(success_message, ephemeral=True)


    async def do_unfollow(self, interaction: discord.Interaction, creator_key: str):
        data = self.tracked_channels[creator_key]
        user_id = data.get("user_id")
        role_id = data.get("role_id")
        creator_name = data.get("creator_name", "Unknown Creator")
        platform = data.get("platform")

        del self.tracked_channels[creator_key]
        self.save_tracked_channels()

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


    async def do_check(self, interaction: discord.Interaction, creator: str, platform: str):
        guild_id = interaction.guild.id

        platform_instance = self.get_platform(platform)
        if not platform_instance:
            await interaction.followup.send(f"❌ Platform **{platform}** is not available.", ephemeral=True)
            return

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

            if hasattr(platform_instance, "clean_description"):
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
            creator_id = await platform_instance.get_channel_id(creator, guild_id)
            if not creator_id:
                await interaction.followup.send("❌ Couldn't find that Twitch channel.", ephemeral=True)
                return

            channel_info = await platform_instance.get_channel_info(creator_id, guild_id)
            if not channel_info:
                await interaction.followup.send("❌ Couldn't fetch Twitch channel information.", ephemeral=True)
                return

            stream_info = await platform_instance.get_latest_content(creator_id, guild_id)
            channel_name = channel_info["display_name"]

            if stream_info:
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

    @app_commands.command(name="creators", description="Follow, unfollow, or check content creators")
    async def creators_panel(self, interaction: discord.Interaction):
        embed = self.build_creators_embed(interaction.guild)
        view = CreatorsDashboard(self, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


class CreatorHandleModal(discord.ui.Modal, title="Creator handle"):
    creator = discord.ui.TextInput(
        label="Creator @handle or ID",
        placeholder="e.g. @pewdiepie or pewdiepie",
        required=True,
        max_length=100,
    )

    def __init__(self, cog: "CreatorVideos", platform: str, on_submit_action):
        super().__init__()
        self.cog = cog
        self.platform = platform
        self.on_submit_action = on_submit_action

    async def on_submit(self, interaction: discord.Interaction):
        if self.on_submit_action == "follow":

            view = FollowOptionsView(self.cog, self.platform, self.creator.value)
            await interaction.response.send_message(
                f"Following **{self.creator.value}** on {PLATFORM_LABEL.get(self.platform, self.platform)}.\n"
                f"Pick a notification channel (defaults to this channel), and optionally a "
                f"user + role to award, then hit **Confirm**.",
                view=view,
                ephemeral=True,
            )
        elif self.on_submit_action == "unfollow":
            await interaction.response.defer(ephemeral=True)
            guild_id = interaction.guild.id
            matches = [
                (key, data) for key, data in self.cog.tracked_channels.items()
                if data.get("platform") == self.platform
                and data.get("creator_input", "").lower() == self.creator.value.lower()
                and data.get("guild_id") == guild_id
            ]
            if not matches:
                await interaction.followup.send(
                    f"❌ **{self.creator.value}** isn't being tracked on {self.platform.title()}.", ephemeral=True
                )
                return
            if len(matches) == 1:
                await self.cog.do_unfollow(interaction, matches[0][0])
            else:

                view = UnfollowPickView(self.cog, matches)
                await interaction.followup.send(
                    f"**{self.creator.value}** is tracked in multiple channels — pick which to stop:",
                    view=view,
                    ephemeral=True,
                )
        elif self.on_submit_action == "check":
            await interaction.response.defer(ephemeral=True)
            await self.cog.do_check(interaction, self.creator.value, self.platform)


PLATFORM_LABEL = {"youtube": "🎥 YouTube", "twitch": "🟣 Twitch"}


class FollowOptionsView(discord.ui.View):

    def __init__(self, cog: "CreatorVideos", platform: str, creator: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.platform = platform
        self.creator = creator
        self.target_channel = None
        self.target_user = None
        self.target_role = None

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Notification channel (defaults to here)",
                       channel_types=[discord.ChannelType.text], min_values=0, max_values=1)
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):


        if select.values:
            raw = select.values[0]
            resolved = interaction.guild.get_channel(raw.id)
            if resolved is None:
                try:
                    resolved = await raw.fetch()
                except discord.HTTPException:
                    resolved = None
            self.target_channel = resolved
        else:
            self.target_channel = None
        await interaction.response.defer()

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="User to award a role (optional)",
                       min_values=0, max_values=1)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.target_user = select.values[0] if select.values else None
        await interaction.response.defer()

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Role to award (optional)",
                       min_values=0, max_values=1)
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.target_role = select.values[0] if select.values else None
        await interaction.response.defer()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = self.target_channel or interaction.channel
        await self.cog.do_follow(
            interaction, self.creator, self.platform, channel,
            user=self.target_user, role=self.target_role,
        )
        for item in self.children:
            item.disabled = True
        try:
            await interaction.edit_original_response(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Cancelled.", view=self)


class UnfollowPickView(discord.ui.View):

    def __init__(self, cog: "CreatorVideos", matches):
        super().__init__(timeout=120)
        self.cog = cog
        options = []
        for key, data in matches[:25]:
            ch = cog.bot.get_channel(data.get("discord_channel_id"))
            label = data.get("creator_name", "Unknown")[:80]
            desc = f"in #{ch.name}" if ch else "channel unknown"
            options.append(discord.SelectOption(label=label, description=desc, value=key))
        self.select_menu.options = options

    @discord.ui.select(placeholder="Which tracked entry to remove?")
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        await self.cog.do_unfollow(interaction, select.values[0])
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)


class CreatorsDashboard(discord.ui.View):
    def __init__(self, cog: "CreatorVideos", guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.selected_platform = None
        self.message: discord.Message = None
        options = self.cog.configured_platform_options(guild_id)
        self.platform_select.options = options or [
            discord.SelectOption(label="No platforms configured — use /platforms", value="none")
        ]
        self.platform_select.disabled = not options

    @discord.ui.select(placeholder="Choose a platform...")
    async def platform_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_platform = select.values[0] if select.values[0] != "none" else None
        await interaction.response.defer()

    @discord.ui.button(label="Follow", style=discord.ButtonStyle.green, emoji="➕")
    async def follow_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_platform(interaction):
            return
        await interaction.response.send_modal(
            CreatorHandleModal(self.cog, self.selected_platform, "follow")
        )

    @discord.ui.button(label="Unfollow", style=discord.ButtonStyle.red, emoji="➖")
    async def unfollow_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_platform(interaction):
            return
        await interaction.response.send_modal(
            CreatorHandleModal(self.cog, self.selected_platform, "unfollow")
        )

    @discord.ui.button(label="List", style=discord.ButtonStyle.blurple, emoji="📋")
    async def list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.build_creators_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed)

    @discord.ui.button(label="Check now", style=discord.ButtonStyle.grey, emoji="🔍")
    async def check_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_platform(interaction):
            return
        await interaction.response.send_modal(
            CreatorHandleModal(self.cog, self.selected_platform, "check")
        )

    async def _require_platform(self, interaction: discord.Interaction) -> bool:
        if not self.selected_platform:
            await interaction.response.send_message("Pick a platform from the dropdown first.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


async def setup(bot):
    cog = CreatorVideos(bot)
    await bot.add_cog(cog)
    return cog
