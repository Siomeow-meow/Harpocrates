import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Select, View

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_command_categories(self):
        categories = {}

        for command in self.bot.tree.walk_commands():
            if command.name == "help":
                continue

            cog = command.binding
            if cog is None:
                cog_name = "General"
            else:
                cog_name = cog.__class__.__name__

            if cog_name == "HelpCog":
                continue

            if cog_name not in categories:
                categories[cog_name] = {
                    'cog': cog,
                    'commands': []
                }

            categories[cog_name]['commands'].append(command)

        return categories

    def get_category_emoji(self, category_name):
        emojis = {
            "CreatorVideos": "🎥",
            "ReactionRole": "🎭",
            "VoiceCog": "🎤",
            "Moderation": "🛡️",
            "General": "📝"
        }
        return emojis.get(category_name, "📝")

    def get_category_description(self, category_name):
        descriptions = {
            "CreatorVideos": "Manage YouTube creator notifications and automatic role assignments",
            "ReactionRole": "Manage automatic role assignment through reactions",
            "VoiceCog": "Manage temporary voice channels",
            "Moderation": "Manage user warnings and timeouts",
            "General": "Miscellaneous commands"
        }
        return descriptions.get(category_name)

    def create_category_embed(self, category_name, commands_data):
        cog = commands_data['cog']
        commands = commands_data['commands']
        emoji = self.get_category_emoji(category_name)
        description = self.get_category_description(category_name)

        embed = discord.Embed(
            title=f"{emoji} {category_name} Commands",
            color=discord.Color.blurple(),
            description=description or "Various commands for this category"
        )

        for command in commands:
            embed.add_field(
                name=f"`/{command.name}`",
                value=command.description or "No description available",
                inline=False
            )

        if hasattr(cog, 'help_footer'):
            embed.set_footer(text=cog.help_footer)
        else:
            embed.set_footer(text=f"Total commands: {len(commands)}")

        return embed

    @app_commands.command(name="help", description="Show all available commands with category selection")
    async def help_command(self, interaction: discord.Interaction):
        categories = self.get_command_categories()

        if not categories:
            await interaction.response.send_message("No commands available.", ephemeral=True)
            return


        embed = discord.Embed(
            title="📚 Command Help Menu",
            color=discord.Color.blurple(),
            description="Select a category from the dropdown below to view specific commands.\n\n"
                        f"**Available Categories ({len(categories)}):**\n" +
                       "\n".join([f"• {self.get_category_emoji(name)} **{name}** - {self.get_category_description(name) or 'Various commands'}"
                                for name in sorted(categories.keys())])
        )
        embed.set_footer(text="Select a category from the dropdown menu below")


        options = []
        for category_name in sorted(categories.keys()):
            emoji = self.get_category_emoji(category_name)
            description = self.get_category_description(category_name) or "Various commands"

            short_desc = description[:50] + "..." if len(description) > 50 else description

            options.append(
                discord.SelectOption(
                    label=category_name,
                    value=category_name,
                    description=short_desc,
                    emoji=emoji
                )
            )


        class HelpDropdown(Select):
            def __init__(self, categories, help_cog):
                self.categories = categories
                self.help_cog = help_cog
                super().__init__(
                    placeholder="Select a category to view commands...",
                    options=options,
                    min_values=1,
                    max_values=1
                )

            async def callback(self, interaction: discord.Interaction):
                selected_category = self.values[0]
                embed = self.help_cog.create_category_embed(selected_category, self.categories[selected_category])

                await interaction.response.edit_message(embed=embed, view=self.view)


        class HelpView(View):
            def __init__(self, categories, help_cog):
                super().__init__(timeout=180)
                self.categories = categories
                self.help_cog = help_cog
                self.add_item(HelpDropdown(categories, help_cog))

            async def on_timeout(self):

                for item in self.children:
                    item.disabled = True

                try:
                    await self.message.edit(view=self)
                except:
                    pass

        view = HelpView(categories, self)


        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
