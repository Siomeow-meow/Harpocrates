import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from db import load_blob, save_blob

COLLECTION = "reaction_roles"


def load_reaction_roles():
    try:
        data = load_blob(COLLECTION)
        result = {}
        for k, v in data.items():
            try:
                result[int(k)] = v
            except ValueError:
                result[k] = v
        if not result:
            print("⚠️ No reaction role data found, starting fresh")
        return result
    except Exception as e:
        print(f"❌ Error loading reaction roles from MongoDB: {e}")
        return {}


def process_description(description: str) -> str:
    if not description:
        return ""
    return description.replace('\\n', '\n')


def parse_color(color: str, default=None):
    if default is None:
        default = discord.Color.blue()
    if not color:
        return default, True
    try:
        return discord.Color(int(color.strip('#'), 16)), True
    except ValueError:
        return default, False


class ReactionRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reaction_roles = load_reaction_roles()
        self.unique_messages = set()
        self._load_unique_messages()
        self.bot.loop.create_task(self.initialize_reactions())


    def _load_unique_messages(self):
        for data in self.reaction_roles.values():
            if data.get("type") == "unique":
                content = f"{data.get('title', '')} {data.get('description', '')}".lower()
                self.unique_messages.add(content)

    def save_reaction_roles(self):
        try:
            json_data = {str(k): v for k, v in self.reaction_roles.items()}
            success = save_blob(COLLECTION, json_data)
            print(f"{'✅' if success else '❌'} Save {'succeeded' if success else 'failed'} "
                  f"({len(self.reaction_roles)} setups)")
            return success
        except Exception as e:
            print(f"❌ Critical error saving reaction roles: {e}")
            return False


    async def initialize_reactions(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)
        await self.restore_reactions()

    async def restore_reactions(self):
        if not self.reaction_roles:
            print("ℹ️ No reaction roles to restore")
            return

        restored_count = 0
        failed_messages = []
        skipped_count = 0

        for message_id, data in self.reaction_roles.items():
            try:
                channel_id = data.get("channel_id")
                reactions = data.get("reactions", {})
                if not channel_id or not reactions:
                    continue
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    failed_messages.append(message_id)
                    continue
                try:
                    message = await channel.fetch_message(message_id)
                except (discord.NotFound, discord.Forbidden):
                    failed_messages.append(message_id)
                    continue

                current_reactions = []
                for reaction in message.reactions:
                    try:
                        async for user in reaction.users(limit=10):
                            if user.id == self.bot.user.id:
                                current_reactions.append(str(reaction.emoji))
                                break
                    except discord.HTTPException:
                        continue

                for emoji in reactions.keys():
                    if emoji in current_reactions:
                        skipped_count += 1
                        continue
                    try:
                        await message.add_reaction(emoji)
                        restored_count += 1
                        await asyncio.sleep(0.25)
                    except discord.HTTPException as e:
                        print(f"❌ Failed to add reaction {emoji} to {message_id}: {e}")
            except Exception as e:
                print(f"❌ Unexpected error restoring {message_id}: {e}")
                failed_messages.append(message_id)

        success_count = len(self.reaction_roles) - len(failed_messages)
        print(f"✅ Restored {restored_count} reactions (skipped {skipped_count}) "
              f"across {success_count}/{len(self.reaction_roles)} messages")

        if failed_messages:
            for msg_id in failed_messages:
                self.reaction_roles.pop(msg_id, None)
            self.save_reaction_roles()

    async def _handle_missing_role(self, message_id, emoji, role_id):
        if message_id in self.reaction_roles and emoji in self.reaction_roles[message_id].get("reactions", {}):
            del self.reaction_roles[message_id]["reactions"][emoji]
            self.save_reaction_roles()


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in self.reaction_roles:
            return

        emoji = str(payload.emoji)
        data = self.reaction_roles[payload.message_id]
        reactions = data.get("reactions", {})
        msg_type = data.get("type", "normal")
        if emoji not in reactions:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role_id = reactions[emoji]
        role = guild.get_role(role_id)
        if not role:
            await self._handle_missing_role(payload.message_id, emoji, role_id)
            return

        member = guild.get_member(payload.user_id)
        if member and not member.bot:
            try:
                if role.position >= guild.me.top_role.position:
                    return
                await member.add_roles(role, reason="Reaction Role")
                if msg_type == "verify":
                    try:
                        channel = self.bot.get_channel(payload.channel_id)
                        if channel:
                            message = await channel.fetch_message(payload.message_id)
                            await message.remove_reaction(payload.emoji, member)
                    except Exception as e:
                        print(f"⚠️ Could not remove verification reaction: {e}")
            except discord.Forbidden:
                print(f"❌ Missing permissions to add {role.name} in {guild.name}")
            except discord.HTTPException as e:
                print(f"❌ Error adding role: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.message_id not in self.reaction_roles:
            return
        emoji = str(payload.emoji)
        data = self.reaction_roles[payload.message_id]
        reactions = data.get("reactions", {})
        if data.get("type") == "verify" or emoji not in reactions:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role = guild.get_role(reactions[emoji])
        if not role:
            return
        member = guild.get_member(payload.user_id)
        if member and not member.bot:
            try:
                if role.position >= guild.me.top_role.position:
                    return
                await member.remove_roles(role, reason="Reaction Role")
            except discord.Forbidden:
                print(f"❌ Missing permissions to remove {role.name} in {guild.name}")
            except discord.HTTPException as e:
                print(f"❌ Error removing role: {e}")


    @app_commands.command(name="reactionroles", description="Open the reaction roles dashboard")
    async def reactionroles(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ You need `Manage Roles` permission to use this.", ephemeral=True
            )
            return
        view = DashboardView(self)
        embed = dashboard_embed(self, interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


def dashboard_embed(cog: ReactionRole, guild: discord.Guild) -> discord.Embed:
    server_messages = [
        (mid, d) for mid, d in cog.reaction_roles.items()
        if cog.bot.get_channel(d.get("channel_id")) and cog.bot.get_channel(d.get("channel_id")).guild.id == guild.id
    ]
    embed = discord.Embed(
        title="🎛️ Reaction Roles Dashboard",
        description=(
            f"**{len(server_messages)}** reaction role message(s) in this server.\n\n"
            "Use the buttons below to create, manage, or maintain your setups."
        ),
        color=discord.Color.blurple(),
    )
    return embed


def message_panel_embed(data: dict, message_id: int, channel: discord.abc.GuildChannel, guild: discord.Guild) -> discord.Embed:
    reactions = data.get("reactions", {})
    embed = discord.Embed(
        title=f"🔍 {data.get('title', 'Untitled')}",
        description=f"**Type:** {data.get('type', 'normal').title()}\n**Channel:** {channel.mention if channel else 'Unknown'}",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Message ID: {message_id}")
    if reactions:
        lines = []
        for emoji, role_id in reactions.items():
            role = guild.get_role(role_id)
            lines.append(f"{emoji} → {role.mention if role else f'Deleted Role ({role_id})'}")
        embed.add_field(name=f"Role Mappings ({len(lines)})", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Role Mappings", value="No roles configured yet.", inline=False)
    return embed


class DashboardView(discord.ui.View):
    def __init__(self, cog: ReactionRole):
        super().__init__(timeout=300)
        self.cog = cog

    async def _check_perms(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ You need `Manage Roles` permission.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Create New", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def create_new(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perms(interaction):
            return
        await interaction.response.send_modal(CreateMessageModal(self.cog))

    @discord.ui.button(label="Manage Existing", emoji="📋", style=discord.ButtonStyle.primary, row=0)
    async def manage_existing(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perms(interaction):
            return
        server_messages = [
            (mid, d) for mid, d in self.cog.reaction_roles.items()
            if self.cog.bot.get_channel(d.get("channel_id"))
            and self.cog.bot.get_channel(d.get("channel_id")).guild.id == interaction.guild.id
        ]
        if not server_messages:
            await interaction.response.send_message("❌ No reaction role messages found in this server.", ephemeral=True)
            return
        view = SelectMessageView(self.cog, server_messages)
        await interaction.response.send_message("Pick a message to manage:", view=view, ephemeral=True)

    @discord.ui.button(label="Cleanup", emoji="🧹", style=discord.ButtonStyle.secondary, row=1)
    async def cleanup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perms(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        cleaned, role_cleaned = 0, 0
        for msg_id in list(self.cog.reaction_roles.keys()):
            data = self.cog.reaction_roles[msg_id]
            channel = self.cog.bot.get_channel(data.get("channel_id"))
            try:
                if channel:
                    await channel.fetch_message(msg_id)
                else:
                    del self.cog.reaction_roles[msg_id]
                    cleaned += 1
                    continue
            except (discord.NotFound, discord.Forbidden):
                del self.cog.reaction_roles[msg_id]
                cleaned += 1
                continue
            for emoji, role_id in list(data.get("reactions", {}).items()):
                if not interaction.guild.get_role(role_id):
                    del data["reactions"][emoji]
                    role_cleaned += 1
        if cleaned or role_cleaned:
            self.cog.save_reaction_roles()
            await interaction.followup.send(
                f"🧹 Cleanup complete. Removed {cleaned} stale message(s), fixed {role_cleaned} role mapping(s).",
                ephemeral=True,
            )
        else:
            await interaction.followup.send("✅ No cleanup needed — everything is valid!", ephemeral=True)

    @discord.ui.button(label="Backup", emoji="💾", style=discord.ButtonStyle.secondary, row=1)
    async def backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perms(interaction):
            return
        try:
            json_data = {str(k): v for k, v in self.cog.reaction_roles.items()}
            success = save_blob(f"{COLLECTION}_backup", json_data)
            if success:
                await interaction.response.send_message(
                    f"✅ Backup saved. **{len(self.cog.reaction_roles)}** setup(s) backed up.", ephemeral=True
                )
            else:
                await interaction.response.send_message("❌ Backup failed.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Backup failed: {e}", ephemeral=True)


class SelectMessageView(discord.ui.View):
    def __init__(self, cog: ReactionRole, server_messages):
        super().__init__(timeout=180)
        self.cog = cog
        options = [
            discord.SelectOption(
                label=(data.get("title") or "Untitled")[:100],
                description=f"{data.get('type', 'normal').title()} • {len(data.get('reactions', {}))} role(s)",
                value=str(mid),
            )
            for mid, data in server_messages[:25]
        ]
        self.select = discord.ui.Select(placeholder="Choose a reaction role message...", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        message_id = int(self.select.values[0])
        data = self.cog.reaction_roles.get(message_id)
        if not data:
            await interaction.response.send_message("❌ That message no longer exists.", ephemeral=True)
            return
        channel = self.cog.bot.get_channel(data.get("channel_id"))
        embed = message_panel_embed(data, message_id, channel, interaction.guild)
        view = MessagePanelView(self.cog, message_id)
        await interaction.response.edit_message(content=None, embed=embed, view=view)


class MessagePanelView(discord.ui.View):
    def __init__(self, cog: ReactionRole, message_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.message_id = message_id

    def _refresh_embed(self, guild: discord.Guild):
        data = self.cog.reaction_roles.get(self.message_id)
        channel = self.cog.bot.get_channel(data.get("channel_id"))
        return message_panel_embed(data, self.message_id, channel, guild)

    @discord.ui.button(label="Edit", emoji="✏️", style=discord.ButtonStyle.primary, row=0)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.cog.reaction_roles.get(self.message_id)
        if not data:
            await interaction.response.send_message("❌ Message no longer tracked.", ephemeral=True)
            return
        await interaction.response.send_modal(EditMessageModal(self.cog, self.message_id, data))

    @discord.ui.button(label="Add Role", emoji="🎭", style=discord.ButtonStyle.success, row=0)
    async def add_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddRoleEmojiModal(self.cog, self.message_id))

    @discord.ui.button(label="Remove Role", emoji="➖", style=discord.ButtonStyle.danger, row=0)
    async def remove_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.cog.reaction_roles.get(self.message_id, {})
        reactions = data.get("reactions", {})
        if not reactions:
            await interaction.response.send_message("❌ No role mappings to remove.", ephemeral=True)
            return
        view = RemoveRoleView(self.cog, self.message_id, reactions)
        await interaction.response.send_message("Pick a mapping to remove:", view=view, ephemeral=True)

    @discord.ui.button(label="Delete Message", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ConfirmDeleteView(self.cog, self.message_id)
        await interaction.response.send_message(
            "⚠️ This will permanently delete the message and its configuration. Are you sure?",
            view=view, ephemeral=True,
        )


class RemoveRoleView(discord.ui.View):
    def __init__(self, cog: ReactionRole, message_id: int, reactions: dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.message_id = message_id
        options = [
            discord.SelectOption(label=f"{emoji}", description=f"Role ID: {role_id}", value=emoji)
            for emoji, role_id in list(reactions.items())[:25]
        ]
        self.select = discord.ui.Select(placeholder="Choose an emoji → role mapping to remove", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        await interaction.response.defer()

        emoji = self.select.values[0]
        data = self.cog.reaction_roles.get(self.message_id)
        if not data or emoji not in data.get("reactions", {}):
            await interaction.edit_original_response(content="❌ That mapping no longer exists.", view=None)
            return
        data["reactions"].pop(emoji, None)
        self.cog.save_reaction_roles()

        channel = self.cog.bot.get_channel(data.get("channel_id"))
        if channel:
            try:
                message = await channel.fetch_message(self.message_id)
                await message.clear_reaction(emoji)
            except discord.HTTPException:
                pass

        await interaction.edit_original_response(content=f"✅ Removed mapping for {emoji}.", view=None)


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, cog: ReactionRole, message_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        data = self.cog.reaction_roles.get(self.message_id)
        if not data:
            await interaction.edit_original_response(content="❌ Already deleted.", view=None)
            return

        if data.get("type") == "unique":
            content = f"{data.get('title', '')} {data.get('description', '')}".lower()
            self.cog.unique_messages.discard(content)

        channel = self.cog.bot.get_channel(data.get("channel_id"))
        deleted = False
        if channel:
            try:
                message = await channel.fetch_message(self.message_id)
                await message.delete()
                deleted = True
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await interaction.edit_original_response(
                    content="❌ I don't have permission to delete that message.", view=None
                )
                return

        del self.cog.reaction_roles[self.message_id]
        self.cog.save_reaction_roles()
        await interaction.edit_original_response(
            content=f"✅ Configuration removed.{' Message deleted.' if deleted else ' (Message was already gone.)'}",
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


class CreateMessageModal(discord.ui.Modal, title="Create Reaction Role Message"):
    msg_title = discord.ui.TextInput(label="Title", max_length=256)
    description = discord.ui.TextInput(
        label="Description", style=discord.TextStyle.paragraph, max_length=2000,
        placeholder="Use \\n for line breaks", required=False,
    )
    color = discord.ui.TextInput(label="Color (hex, optional)", placeholder="#5865F2", required=False, max_length=7)
    msg_type = discord.ui.TextInput(
        label="Type: normal / unique / verify", default="normal", max_length=10, required=False
    )

    def __init__(self, cog: ReactionRole):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        type_value = (self.msg_type.value or "normal").strip().lower()
        if type_value not in ("normal", "unique", "verify"):
            await interaction.followup.send(
                "❌ Type must be `normal`, `unique`, or `verify`.", ephemeral=True
            )
            return

        if type_value == "unique":
            content = f"{self.msg_title.value} {self.description.value}".lower()
            if content in self.cog.unique_messages:
                await interaction.followup.send(
                    "❌ A unique message with this content already exists.", ephemeral=True
                )
                return
            self.cog.unique_messages.add(content)

        embed_color, valid = parse_color(self.color.value)
        processed_desc = process_description(self.description.value)

        if type_value == "verify":
            embed = discord.Embed(title="🔐 " + self.msg_title.value, description=processed_desc, color=discord.Color.gold())
            embed.set_footer(text="React to verify yourself")
        else:
            embed = discord.Embed(title=self.msg_title.value, description=processed_desc, color=embed_color)
            embed.set_footer(text="React to get roles • Remove reaction to remove roles")

        try:
            message = await interaction.channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("❌ I can't send messages in this channel.", ephemeral=True)
            return

        self.cog.reaction_roles[message.id] = {
            "reactions": {},
            "type": type_value,
            "channel_id": interaction.channel.id,
            "title": self.msg_title.value,
            "description": self.description.value,
            "color": self.color.value,
        }
        self.cog.save_reaction_roles()

        note = "" if valid else "\n⚠️ Invalid color format — used default blue instead."
        await interaction.followup.send(
            f"✅ Created! Message ID `{message.id}`. Use **Manage Existing** to add role mappings.{note}",
            ephemeral=True,
        )


class EditMessageModal(discord.ui.Modal, title="Edit Reaction Role Message"):
    def __init__(self, cog: ReactionRole, message_id: int, data: dict):
        super().__init__()
        self.cog = cog
        self.message_id = message_id
        self.msg_title = discord.ui.TextInput(label="Title", default=data.get("title", ""), max_length=256, required=False)
        self.description = discord.ui.TextInput(
            label="Description", style=discord.TextStyle.paragraph, max_length=2000,
            default=data.get("description", ""), required=False,
        )
        self.color = discord.ui.TextInput(label="Color (hex)", default=data.get("color") or "", required=False, max_length=7)
        self.add_item(self.msg_title)
        self.add_item(self.description)
        self.add_item(self.color)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        data = self.cog.reaction_roles.get(self.message_id)
        if not data:
            await interaction.followup.send("❌ This message is no longer tracked.", ephemeral=True)
            return

        channel = self.cog.bot.get_channel(data.get("channel_id"))
        if not channel:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
            return
        try:
            message = await channel.fetch_message(self.message_id)
        except (discord.NotFound, discord.Forbidden):
            await interaction.followup.send("❌ Couldn't fetch the original message.", ephemeral=True)
            return

        old_embed = message.embeds[0] if message.embeds else discord.Embed()
        new_embed = discord.Embed()
        new_embed.title = self.msg_title.value or old_embed.title
        new_embed.description = process_description(self.description.value) if self.description.value else old_embed.description

        new_color, valid = parse_color(self.color.value, default=old_embed.color or discord.Color.blue())
        new_embed.color = new_color
        if old_embed.footer:
            new_embed.set_footer(text=old_embed.footer.text)

        await message.edit(embed=new_embed)

        if self.msg_title.value:
            data["title"] = self.msg_title.value
        if self.description.value:
            data["description"] = self.description.value
        if self.color.value:
            data["color"] = self.color.value
        self.cog.save_reaction_roles()

        note = "" if valid else "\n⚠️ Invalid color format — kept previous color."
        embed = message_panel_embed(data, self.message_id, channel, interaction.guild)
        await interaction.followup.send(f"✅ Updated.{note}", embed=embed, ephemeral=True)


class AddRoleEmojiModal(discord.ui.Modal, title="Add Role Mapping — Step 1"):
    emoji = discord.ui.TextInput(label="Emoji", placeholder="🎮 or a custom emoji", max_length=100)

    def __init__(self, cog: ReactionRole, message_id: int):
        super().__init__()
        self.cog = cog
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        data = self.cog.reaction_roles.get(self.message_id)
        if not data:
            await interaction.response.send_message("❌ Message no longer tracked.", ephemeral=True)
            return
        if self.emoji.value in data.get("reactions", {}):
            await interaction.response.send_message(f"❌ {self.emoji.value} is already used on this message.", ephemeral=True)
            return


        view = PickRoleView(self.cog, self.message_id, self.emoji.value)
        await interaction.response.send_message(
            f"Now pick which role {self.emoji.value} should grant:", view=view, ephemeral=True
        )


class PickRoleView(discord.ui.View):
    def __init__(self, cog: ReactionRole, message_id: int, emoji: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.message_id = message_id
        self.emoji = emoji

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Choose a role...")
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):


        await interaction.response.defer()

        role = select.values[0]
        data = self.cog.reaction_roles.get(self.message_id)
        if not data:
            await interaction.edit_original_response(content="❌ Message no longer tracked.", view=None)
            return

        if role.position >= interaction.guild.me.top_role.position:
            await interaction.edit_original_response(
                content="❌ I can't manage that role — it's higher than my highest role.", view=None
            )
            return

        channel = self.cog.bot.get_channel(data.get("channel_id"))
        try:
            message = await channel.fetch_message(self.message_id)
            await message.add_reaction(self.emoji)
        except (discord.HTTPException, discord.NotFound, discord.Forbidden):
            await interaction.edit_original_response(content="❌ Couldn't add that reaction to the message.", view=None)
            return

        data["reactions"][self.emoji] = role.id
        self.cog.save_reaction_roles()
        await interaction.edit_original_response(
            content=f"✅ {self.emoji} now grants {role.mention}.", view=None
        )


async def setup(bot):
    await bot.add_cog(ReactionRole(bot))
