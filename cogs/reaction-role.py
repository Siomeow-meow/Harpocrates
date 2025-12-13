import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
import tempfile

REACTION_ROLES_FILE = "data/reaction_roles.json"

class ReactionRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reaction_roles = self.load_reaction_roles()
        self.unique_messages = set()
        self._load_unique_messages()
        # Create a task to restore reactions when bot is ready
        self.bot.loop.create_task(self.initialize_reactions())

    async def initialize_reactions(self):
        """Initialize reactions after bot is ready"""
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)  # Small delay to ensure everything is loaded
        await self.restore_reactions()

    def _load_unique_messages(self):
        """Load unique messages from current reaction roles"""
        for data in self.reaction_roles.values():
            if data.get("type") == "unique":
                message_content = f"{data.get('title', '')} {data.get('description', '')}".lower()
                self.unique_messages.add(message_content)

    def load_reaction_roles(self):
        """Load reaction roles from JSON file with multiple fallback options"""
        # Try primary file first
        if os.path.exists(REACTION_ROLES_FILE):
            try:
                with open(REACTION_ROLES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert string keys to integers
                    result = {}
                    for k, v in data.items():
                        try:
                            result[int(k)] = v
                        except ValueError:
                            result[k] = v
                    return result
            except (json.JSONDecodeError, ValueError) as e:
                print(f"❌ Error loading {REACTION_ROLES_FILE}: {e}")
                return {}
        
        print("⚠️ No reaction role data found, starting fresh")
        return {}

    def _atomic_save(self, data):
        """Atomic save operation to prevent data corruption"""
        tmp_path = None
        try:
            # Write to temporary file first
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json', delete=False) as tmp:
                # Convert all keys to strings for JSON serialization
                json_data = {str(k): v for k, v in data.items()}
                json.dump(json_data, tmp, indent=4, ensure_ascii=False)
                tmp_path = tmp.name
            
            # Replace original file
            os.replace(tmp_path, REACTION_ROLES_FILE)
            return True
        except Exception as e:
            print(f"❌ Atomic save failed: {e}")
            # Clean up temp file if it exists
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return False

    def save_reaction_roles(self):
        """Save current reaction roles with robust error handling"""
        try:
            # Create backup before saving
            if os.path.exists(REACTION_ROLES_FILE):
                backup_file = REACTION_ROLES_FILE + '.bak'
                try:
                    os.replace(REACTION_ROLES_FILE, backup_file)
                    print(f"✅ Created backup: {backup_file}")
                except Exception as e:
                    print(f"⚠️ Could not create backup: {e}")
            
            # Save current data
            success = self._atomic_save(self.reaction_roles)
            if success:
                print(f"✅ Saved {len(self.reaction_roles)} reaction role setups")
            else:
                print("❌ Failed to save reaction roles")
            return success
            
        except Exception as e:
            print(f"❌ Critical error saving reaction roles: {e}")
            return False

    def process_description(self, description: str) -> str:
        """Convert \n to actual line breaks in description"""
        if not description:
            return ""
        return description.replace('\\n', '\n')

    async def restore_reactions(self):
        """Restore reactions to messages after bot restart with better error handling"""
        if not self.reaction_roles:
            print("ℹ️ No reaction roles to restore")
            return
            
        restored_count = 0
        failed_messages = []
        
        for message_id, data in self.reaction_roles.items():
            try:
                channel_id = data.get("channel_id")
                reactions = data.get("reactions", {})
                
                if not channel_id or not reactions:
                    print(f"⚠️ Skipping message {message_id}: missing channel_id or reactions")
                    continue
                    
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    print(f"❌ Channel {channel_id} not found for message {message_id}")
                    failed_messages.append(message_id)
                    continue
                
                # Fetch the message
                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    print(f"❌ Message {message_id} not found in channel {channel.name}")
                    failed_messages.append(message_id)
                    continue
                except discord.Forbidden:
                    print(f"❌ No permission to access message {message_id} in channel {channel.name}")
                    failed_messages.append(message_id)
                    continue
                
                # Clear existing reactions from bot only
                try:
                    await message.clear_reactions()
                except discord.Forbidden:
                    print(f"⚠️ Cannot clear reactions for message {message_id}")
                    # Continue anyway, we'll try to add our reactions
                
                # Add configured reactions with rate limiting
                for emoji in reactions.keys():
                    try:
                        await message.add_reaction(emoji)
                        restored_count += 1
                        # Respect rate limits
                        await asyncio.sleep(0.25)
                    except (discord.HTTPException, discord.InvalidArgument) as e:
                        print(f"❌ Failed to add reaction {emoji} to message {message_id}: {e}")
                        
            except Exception as e:
                print(f"❌ Unexpected error restoring message {message_id}: {e}")
                failed_messages.append(message_id)
        
        # Summary
        success_count = len(self.reaction_roles) - len(failed_messages)
        print(f"✅ Successfully restored {restored_count} reactions across {success_count}/{len(self.reaction_roles)} messages")
        
        if failed_messages:
            print(f"❌ Failed to restore {len(failed_messages)} messages: {failed_messages}")
            
        # Optional: Clean up failed messages from storage
        if failed_messages:
            self._cleanup_failed_messages(failed_messages)

    def _cleanup_failed_messages(self, failed_message_ids):
        """Remove messages that no longer exist from storage"""
        cleaned_count = 0
        for msg_id in failed_message_ids:
            if msg_id in self.reaction_roles:
                del self.reaction_roles[msg_id]
                cleaned_count += 1
        
        if cleaned_count > 0:
            self.save_reaction_roles()
            print(f"🧹 Cleaned {cleaned_count} non-existent messages from storage")

    async def _handle_missing_role(self, message_id, emoji, role_id):
        """Handle cases where a role no longer exists"""
        print(f"🗑️ Removing invalid role mapping: {emoji} -> {role_id}")
        if message_id in self.reaction_roles and emoji in self.reaction_roles[message_id].get("reactions", {}):
            del self.reaction_roles[message_id]["reactions"][emoji]
            self.save_reaction_roles()

    # MESSAGE CREATION COMMAND
    @app_commands.command(name="rr_create", description="Create a new reaction role message")
    @app_commands.describe(
        title="The title for your embed message",
        description="The description for your embed message (use \\n for line breaks)",
        message_type="The type of message",
        color="Hex color for the embed (e.g., #FF0000)"
    )
    @app_commands.choices(message_type=[
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="Unique", value="unique"),
        app_commands.Choice(name="Verify", value="verify")
    ])
    async def rr_create(self, interaction: discord.Interaction, title: str, description: str, message_type: app_commands.Choice[str], color: str = None):
        """Create a new reaction role message with better feedback"""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return

        if message_type.value == "unique":
            message_content = f"{title} {description}".lower()
            if message_content in self.unique_messages:
                await interaction.followup.send("❌ A unique message with this content already exists.", ephemeral=True)
                return
            self.unique_messages.add(message_content)
        
        # Parse color
        embed_color = discord.Color.blue()
        if color:
            try:
                embed_color = discord.Color(int(color.strip('#'), 16))
            except ValueError:
                await interaction.followup.send("⚠️ Invalid color format, using default blue.", ephemeral=True)
        
        # Process description to convert \n to actual line breaks
        processed_description = self.process_description(description)
        
        # Create embed based on type
        if message_type.value == "verify":
            embed = discord.Embed(
                title="🔐 " + title,
                description=processed_description,
                color=discord.Color.gold()
            )
            embed.set_footer(text="React to verify yourself")
        else:
            embed = discord.Embed(
                title=title,
                description=processed_description,
                color=embed_color
            )
            embed.set_footer(text="React to get roles • Remove reaction to remove roles")
        
        try:
            message = await interaction.channel.send(embed=embed)
            
            self.reaction_roles[message.id] = {
                "reactions": {},
                "type": message_type.value,
                "channel_id": interaction.channel.id,
                "title": title,
                "description": description,  # Store original description with \n
                "color": color
            }
            
            self.save_reaction_roles()
            
            success_embed = discord.Embed(
                title="✅ Reaction Role Created",
                description=f"**Message ID:** `{message.id}`\n**Type:** {message_type.value.title()}",
                color=discord.Color.green()
            )
            success_embed.add_field(
                name="Next Steps", 
                value=f"Use `/rr_add {message.id} <emoji> <role>` to add roles",
                inline=False
            )
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to send messages in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="rr_edit", description="Edit an existing reaction role message")
    @app_commands.describe(
        message_id="The ID of the message to edit",
        title="New title for the embed",
        description="New description for the embed (use \\n for line breaks)",
        color="New hex color for the embed (e.g., #FF0000)",
        channel="The channel where the message is located"
    )
    async def rr_edit(self, interaction: discord.Interaction, message_id: str, title: str = None, description: str = None, color: str = None, channel: discord.TextChannel = None):
        """Edit an existing reaction role message"""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return

        try:
            message_id_int = int(message_id)
            target_channel = channel or interaction.channel
            
            if message_id_int not in self.reaction_roles:
                await interaction.followup.send("❌ No reaction role setup found for this message.", ephemeral=True)
                return
            
            # Fetch the message
            try:
                message = await target_channel.fetch_message(message_id_int)
            except discord.NotFound:
                await interaction.followup.send("❌ Message not found in the specified channel.", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.followup.send("❌ I don't have permission to access that channel.", ephemeral=True)
                return
            
            # Get current embed
            if not message.embeds:
                await interaction.followup.send("❌ This message doesn't have an embed to edit.", ephemeral=True)
                return
            
            old_embed = message.embeds[0]
            data = self.reaction_roles[message_id_int]
            
            # Create new embed with updated fields
            new_embed = discord.Embed()
            
            # Update title
            new_embed.title = title if title else old_embed.title
            if not new_embed.title and title:
                new_embed.title = title
            
            # Update description - process \n to actual line breaks
            if description is not None:
                processed_description = self.process_description(description)
                new_embed.description = processed_description
            else:
                new_embed.description = old_embed.description
            
            # Update color
            if color:
                try:
                    new_embed.color = discord.Color(int(color.strip('#'), 16))
                except ValueError:
                    await interaction.followup.send("⚠️ Invalid color format, keeping current color.", ephemeral=True)
                    new_embed.color = old_embed.color
            else:
                new_embed.color = old_embed.color
            
            # Copy footer and other properties
            if old_embed.footer:
                new_embed.set_footer(text=old_embed.footer.text)
            
            # Update the message
            await message.edit(embed=new_embed)
            
            # Update stored data
            if title:
                data["title"] = title
            if description is not None:  # Explicitly check for None to allow empty strings
                data["description"] = description  # Store original with \n
            if color:
                data["color"] = color
            
            self.save_reaction_roles()
            
            success_embed = discord.Embed(
                title="✅ Reaction Role Updated",
                description=f"**Message ID:** `{message_id}`",
                color=discord.Color.green()
            )
            if title:
                success_embed.add_field(name="New Title", value=title, inline=False)
            if description is not None:
                # Show processed description in the success message
                success_embed.add_field(name="New Description", value=self.process_description(description) or "*Empty*", inline=False)
            if color:
                success_embed.add_field(name="New Color", value=color, inline=False)
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)

    @app_commands.command(name="rr_delete", description="Delete a reaction role message completely")
    @app_commands.describe(
        message_id="The ID of the message to delete",
        channel="The channel where the message is located"
    )
    async def rr_delete(self, interaction: discord.Interaction, message_id: str, channel: discord.TextChannel = None):
        """Completely remove a reaction role setup and delete the message"""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return

        try:
            message_id_int = int(message_id)
            target_channel = channel or interaction.channel
            
            if message_id_int not in self.reaction_roles:
                await interaction.followup.send("❌ No reaction role setup found for this message.", ephemeral=True)
                return
            
            data = self.reaction_roles[message_id_int]
            
            # Remove from unique messages if applicable
            if data.get("type") == "unique":
                message_content = f"{data.get('title', '')} {data.get('description', '')}".lower()
                if message_content in self.unique_messages:
                    self.unique_messages.remove(message_content)
            
            # ALWAYS try to delete the Discord message
            message_deleted = False
            try:
                message = await target_channel.fetch_message(message_id_int)
                await message.delete()
                message_deleted = True
                print(f"✅ Deleted reaction role message {message_id_int} from channel {target_channel.name}")
            except discord.NotFound:
                await interaction.followup.send("⚠️ Message not found, but removing from configuration.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("❌ I don't have permission to delete messages in that channel.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to delete message: {e}", ephemeral=True)
                return
            
            # Remove from configuration
            del self.reaction_roles[message_id_int]
            self.save_reaction_roles()
            
            success_embed = discord.Embed(
                title="✅ Reaction Role Deleted",
                description=f"**Message ID:** `{message_id}`\n**Message Deleted:** {'Yes' if message_deleted else 'No'}",
                color=discord.Color.green()
            )
            success_embed.add_field(
                name="Removed Configuration",
                value=f"**Reactions:** {len(data.get('reactions', {}))}\n**Type:** {data.get('type', 'normal')}",
                inline=False
            )
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)

    # ROLE MANAGEMENT COMMANDS
    @app_commands.command(name="rr_add", description="Add an emoji role to a message")
    @app_commands.describe(
        message_id="The ID of the message to add reaction to",
        emoji="The emoji to use for the reaction",
        role="The role to assign when this emoji is clicked",
        channel="The channel where the message is located"
    )
    async def rr_add(self, interaction: discord.Interaction, message_id: str, emoji: str, 
                    role: discord.Role, channel: discord.TextChannel = None):
        """Add a reaction role to an existing message with better validation"""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return
        
        # Validate bot can manage the role
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.followup.send("❌ I cannot manage this role. It's higher than my highest role.", ephemeral=True)
            return

        try:
            message_id_int = int(message_id)
            target_channel = channel or interaction.channel
            
            try:
                message = await target_channel.fetch_message(message_id_int)
                
                # Check if emoji is valid
                try:
                    await message.add_reaction(emoji)
                except (discord.HTTPException, discord.InvalidArgument):
                    await interaction.followup.send("❌ Invalid emoji or cannot use this emoji.", ephemeral=True)
                    return
                
                # Initialize message data if not exists
                if message_id_int not in self.reaction_roles:
                    self.reaction_roles[message_id_int] = {
                        "reactions": {},
                        "type": "normal",
                        "channel_id": target_channel.id
                    }
                
                # Check if emoji already used
                if emoji in self.reaction_roles[message_id_int]["reactions"]:
                    await interaction.followup.send(f"❌ Emoji {emoji} is already used in this message.", ephemeral=True)
                    return
                
                # Add reaction role
                self.reaction_roles[message_id_int]["reactions"][emoji] = role.id
                self.save_reaction_roles()
                
                success_embed = discord.Embed(
                    title="✅ Reaction Role Added",
                    description=f"**Emoji:** {emoji}\n**Role:** {role.mention}",
                    color=discord.Color.green()
                )
                success_embed.add_field(
                    name="Message Info",
                    value=f"**ID:** `{message_id}`\n**Channel:** {target_channel.mention}",
                    inline=False
                )
                
                await interaction.followup.send(embed=success_embed, ephemeral=True)
                
            except discord.NotFound:
                await interaction.followup.send("❌ Message not found in the specified channel.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("❌ I don't have permission to access that channel or add reactions.", ephemeral=True)
                
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)

    @app_commands.command(name="rr_remove", description="Remove a reaction role from a message")
    @app_commands.describe(
        message_id="The ID of the message",
        emoji="The emoji to remove",
        channel="The channel where the message is located"
    )
    async def rr_remove(self, interaction: discord.Interaction, message_id: str, emoji: str, channel: discord.TextChannel = None):
        """Remove a specific reaction role from a message"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            message_id_int = int(message_id)
            target_channel = channel or interaction.channel
            
            if message_id_int not in self.reaction_roles:
                await interaction.followup.send("❌ No reaction role setup found for this message.", ephemeral=True)
                return
            
            data = self.reaction_roles[message_id_int]
            if emoji not in data.get("reactions", {}):
                await interaction.followup.send(f"❌ Emoji {emoji} not found in this reaction role setup.", ephemeral=True)
                return
            
            # Remove from configuration
            role_id = data["reactions"].pop(emoji)
            self.save_reaction_roles()
            
            # Try to remove reaction from message
            try:
                message = await target_channel.fetch_message(message_id_int)
                await message.clear_reaction(emoji)
            except discord.HTTPException:
                pass  # Ignore if we can't remove the reaction
            
            role = interaction.guild.get_role(role_id)
            role_name = role.name if role else "Unknown Role"
            
            success_embed = discord.Embed(
                title="✅ Reaction Role Removed",
                description=f"**Emoji:** {emoji}\n**Role:** {role_name}",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)

    # ROLE CREATION/DELETION COMMANDS
    @app_commands.command(name="role_create", description="Create a new server role")
    @app_commands.describe(
        name="Name of the role",
        color="Hex color for the role (e.g., #FF0000)",
        hoist="Whether the role should be displayed separately",
        mentionable="Whether the role can be mentioned by everyone"
    )
    async def role_create(self, interaction: discord.Interaction, name: str, color: str = None, hoist: bool = False, mentionable: bool = False):
        """Create a new role in the server"""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return
        
        # Check bot permissions
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.followup.send("❌ I don't have permission to manage roles.", ephemeral=True)
            return
        
        try:
            # Parse color
            role_color = discord.Color.default()
            if color:
                try:
                    role_color = discord.Color(int(color.strip('#'), 16))
                except ValueError:
                    await interaction.followup.send("⚠️ Invalid color format, using default color.", ephemeral=True)
            
            # Create the role
            role = await interaction.guild.create_role(
                name=name,
                color=role_color,
                hoist=hoist,
                mentionable=mentionable,
                reason=f"Role created by {interaction.user}"
            )
            
            success_embed = discord.Embed(
                title="✅ Role Created",
                description=f"**Role:** {role.mention}",
                color=discord.Color.green()
            )
            success_embed.add_field(name="Name", value=role.name, inline=True)
            success_embed.add_field(name="Color", value=str(role.color), inline=True)
            success_embed.add_field(name="Position", value=role.position, inline=True)
            success_embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
            success_embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
            success_embed.add_field(name="ID", value=f"`{role.id}`", inline=True)
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create roles.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Failed to create role: {e}", ephemeral=True)

    @app_commands.command(name="role_delete", description="Delete a server role")
    @app_commands.describe(
        role="The role to delete"
    )
    async def role_delete(self, interaction: discord.Interaction, role: discord.Role):
        """Delete a role from the server"""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return
        
        # Check bot permissions
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.followup.send("❌ I don't have permission to manage roles.", ephemeral=True)
            return
        
        # Prevent deleting managed roles or @everyone
        if role.managed or role.is_default():
            await interaction.followup.send("❌ Cannot delete managed or default roles.", ephemeral=True)
            return
        
        # Check role hierarchy
        if role.position >= interaction.user.top_role.position and interaction.user != interaction.guild.owner:
            await interaction.followup.send("❌ You can only delete roles below your highest role.", ephemeral=True)
            return
        
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.followup.send("❌ I cannot delete roles higher than my highest role.", ephemeral=True)
            return
        
        try:
            role_name = role.name
            role_id = role.id
            
            # Check if role is used in any reaction roles
            used_in_messages = []
            for msg_id, data in self.reaction_roles.items():
                if str(role.id) in [str(r_id) for r_id in data.get("reactions", {}).values()]:
                    used_in_messages.append(msg_id)
            
            # Delete the role
            await role.delete(reason=f"Role deleted by {interaction.user}")
            
            success_embed = discord.Embed(
                title="✅ Role Deleted",
                description=f"**Role:** {role_name}",
                color=discord.Color.green()
            )
            success_embed.add_field(name="ID", value=f"`{role_id}`", inline=True)
            
            if used_in_messages:
                success_embed.add_field(
                    name="⚠️ Cleanup Needed", 
                    value=f"This role was used in {len(used_in_messages)} reaction role message(s). Use `/rr_info` to check and update them.",
                    inline=False
                )
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete this role.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Failed to delete role: {e}", ephemeral=True)

    # UTILITY COMMANDS
    @app_commands.command(name="rr_list", description="List all reaction role messages in this server")
    async def rr_list(self, interaction: discord.Interaction):
        """List all reaction role setups in the server"""
        await interaction.response.defer(ephemeral=True)
        
        server_messages = []
        for msg_id, data in self.reaction_roles.items():
            channel = self.bot.get_channel(data.get("channel_id"))
            if channel and channel.guild.id == interaction.guild.id:
                server_messages.append((msg_id, data, channel))
        
        if not server_messages:
            await interaction.followup.send("❌ No reaction role messages found in this server.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Reaction Role Messages",
            description=f"Found {len(server_messages)} setup(s) in this server",
            color=discord.Color.blue()
        )
        
        for msg_id, data, channel in server_messages[:10]:  # Limit to first 10
            reaction_count = len(data.get("reactions", {}))
            embed.add_field(
                name=f"`{msg_id}` - {data.get('type', 'normal').title()}",
                value=f"**Channel:** {channel.mention}\n**Reactions:** {reaction_count}",
                inline=False
            )
        
        if len(server_messages) > 10:
            embed.set_footer(text=f"Showing 10 out of {len(server_messages)} messages")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="rr_info", description="Get detailed info about a reaction role message")
    @app_commands.describe(
        message_id="The ID of the message to check",
        channel="The channel where the message is located"
    )
    async def rr_info(self, interaction: discord.Interaction, message_id: str, channel: discord.TextChannel = None):
        """Get detailed information about a specific reaction role setup"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            message_id_int = int(message_id)
            target_channel = channel or interaction.channel
            
            if message_id_int not in self.reaction_roles:
                await interaction.followup.send("❌ No reaction role setup found for this message.", ephemeral=True)
                return
            
            data = self.reaction_roles[message_id_int]
            reactions = data.get("reactions", {})
            
            embed = discord.Embed(
                title="🔍 Reaction Role Info",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Message ID", value=f"`{message_id}`", inline=True)
            embed.add_field(name="Type", value=data.get("type", "normal").title(), inline=True)
            embed.add_field(name="Channel", value=target_channel.mention, inline=True)
            
            if reactions:
                roles_info = []
                for emoji, role_id in reactions.items():
                    role = interaction.guild.get_role(role_id)
                    role_name = role.mention if role else f"Deleted Role ({role_id})"
                    roles_info.append(f"{emoji} → {role_name}")
                
                embed.add_field(
                    name=f"Role Mappings ({len(roles_info)})",
                    value="\n".join(roles_info) if roles_info else "No roles configured",
                    inline=False
                )
            else:
                embed.add_field(name="Role Mappings", value="No roles configured yet", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)

    @app_commands.command(name="rr_cleanup", description="Clean up invalid reaction role configurations")
    async def rr_cleanup(self, interaction: discord.Interaction):
        """Clean up reaction roles that reference missing messages or roles"""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return
        
        cleaned_count = 0
        role_cleaned_count = 0
        
        for msg_id in list(self.reaction_roles.keys()):
            data = self.reaction_roles[msg_id]
            channel_id = data.get("channel_id")
            channel = self.bot.get_channel(channel_id)
            
            # Check if message still exists
            try:
                if channel:
                    await channel.fetch_message(msg_id)
                else:
                    # Channel not found, remove configuration
                    del self.reaction_roles[msg_id]
                    cleaned_count += 1
                    continue
            except (discord.NotFound, discord.Forbidden):
                # Message not found or no access, remove configuration
                del self.reaction_roles[msg_id]
                cleaned_count += 1
                continue
            
            # Check if roles still exist
            reactions = data.get("reactions", {})
            for emoji, role_id in list(reactions.items()):
                role = interaction.guild.get_role(role_id)
                if not role:
                    del reactions[emoji]
                    role_cleaned_count += 1
        
        if cleaned_count > 0 or role_cleaned_count > 0:
            self.save_reaction_roles()
            embed = discord.Embed(
                title="🧹 Cleanup Complete",
                color=discord.Color.orange()
            )
            if cleaned_count > 0:
                embed.add_field(name="Messages Removed", value=cleaned_count, inline=True)
            if role_cleaned_count > 0:
                embed.add_field(name="Role Mappings Fixed", value=role_cleaned_count, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("✅ No cleanup needed - all configurations are valid!", ephemeral=True)

    @app_commands.command(name="rr_backup", description="Create a backup of reaction role data")
    async def rr_backup(self, interaction: discord.Interaction):
        """Create a manual backup of reaction role data"""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.followup.send("❌ You need `Manage Roles` permission to use this command.", ephemeral=True)
            return
        
        try:
            backup_file = REACTION_ROLES_FILE + '.backup'
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(self.reaction_roles, f, indent=4, ensure_ascii=False)
            
            embed = discord.Embed(
                title="✅ Backup Created",
                description=f"Backup saved to `{backup_file}`",
                color=discord.Color.green()
            )
            embed.add_field(name="Total Setups", value=len(self.reaction_roles), inline=True)
            embed.add_field(name="Total Reactions", value=sum(len(data.get("reactions", {})) for data in self.reaction_roles.values()), inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create backup: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reaction add for role assignment with comprehensive error handling"""
        if payload.user_id == self.bot.user.id:
            return
            
        if payload.message_id in self.reaction_roles:
            emoji = str(payload.emoji)
            data = self.reaction_roles[payload.message_id]
            reactions = data.get("reactions", {})
            msg_type = data.get("type", "normal")
            
            if emoji in reactions:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    print(f"❌ Guild {payload.guild_id} not found")
                    return
                    
                role_id = reactions[emoji]
                role = guild.get_role(role_id)
                
                if not role:
                    print(f"❌ Role {role_id} not found in guild {guild.name}")
                    # Optionally remove the invalid reaction role
                    await self._handle_missing_role(payload.message_id, emoji, role_id)
                    return
                
                member = guild.get_member(payload.user_id)
                if member and not member.bot:
                    try:
                        # Check if bot can manage this role
                        if role.position >= guild.me.top_role.position:
                            print(f"❌ Cannot assign role {role.name} - it's higher than my highest role")
                            return
                            
                        await member.add_roles(role, reason="Reaction Role")
                        print(f"✅ Added {role.name} to {member.display_name} in {guild.name}")
                        
                        # Handle verification type - remove reaction after adding role
                        if msg_type == "verify":
                            try:
                                channel = self.bot.get_channel(payload.channel_id)
                                if channel:
                                    message = await channel.fetch_message(payload.message_id)
                                    await message.remove_reaction(payload.emoji, member)
                                    print(f"🔐 Removed verification reaction for {member.display_name}")
                            except Exception as e:
                                print(f"⚠️ Could not remove verification reaction: {e}")
                                
                    except discord.Forbidden:
                        print(f"❌ Missing permissions to add {role.name} in {guild.name}")
                    except discord.HTTPException as e:
                        print(f"❌ Error adding role to {member.display_name}: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle reaction remove for role removal with better error handling"""
        if payload.message_id in self.reaction_roles:
            emoji = str(payload.emoji)
            data = self.reaction_roles[payload.message_id]
            reactions = data.get("reactions", {})
            msg_type = data.get("type", "normal")
            
            # Don't remove roles for verification type or if reaction remove is disabled
            if msg_type == "verify":
                return
                
            if emoji in reactions:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                    
                role_id = reactions[emoji]
                role = guild.get_role(role_id)
                
                if not role:
                    return
                
                member = guild.get_member(payload.user_id)
                if member and not member.bot:
                    try:
                        # Check if bot can manage this role
                        if role.position >= guild.me.top_role.position:
                            print(f"❌ Cannot remove role {role.name} - it's higher than my highest role")
                            return
                            
                        await member.remove_roles(role, reason="Reaction Role")
                        print(f"✅ Removed {role.name} from {member.display_name} in {guild.name}")
                    except discord.Forbidden:
                        print(f"❌ Missing permissions to remove {role.name} in {guild.name}")
                    except discord.HTTPException as e:
                        print(f"❌ Error removing role from {member.display_name}: {e}")

async def setup(bot):
    await bot.add_cog(ReactionRole(bot))