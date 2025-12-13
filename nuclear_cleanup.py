"""
NUCLEAR CLEANUP - Run this to completely reset Discord command cache
Run this → Wait 2-5 minutes → Run main.py
"""
import discord
from discord.ext import commands
from apikeys import BOTTOKEN
import asyncio

class CleanupBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
    
    async def setup_hook(self):
        print("🧹 NUCLEAR CLEANUP STARTED")
        print("=" * 60)
        
        # Your guild ID
        GUILD_ID = 1132596556198051950
        guild = discord.Object(id=GUILD_ID)
        
        try:
            # 1. SYNC EMPTY GLOBAL COMMANDS FIRST (Most Important!)
            print("1. Syncing EMPTY global commands...")
            self.tree.clear_commands(guild=None)  # Clear global
            await self.tree.sync()  # Sync empty global commands
            print("   ✅ Global commands cleared and synced")
            
            # 2. SYNC EMPTY GUILD COMMANDS
            print("2. Syncing EMPTY guild commands...")
            self.tree.clear_commands(guild=guild)  # Clear guild
            await self.tree.sync(guild=guild)  # Sync empty guild commands
            print(f"   ✅ Guild {GUILD_ID} commands cleared and synced")
            
            # 3. Clear internal command tree
            print("3. Clearing internal command tree...")
            # Get all command names
            command_names = []
            
            # Global commands
            for cmd_name, cmd in list(self.tree._global_commands.items()):
                command_names.append(cmd_name)
                self.tree.remove_command(cmd_name, guild=None)
            
            # Guild commands
            if guild.id in self.tree._guild_commands:
                for cmd_name, cmd in list(self.tree._guild_commands[guild.id].items()):
                    if cmd_name not in command_names:
                        command_names.append(cmd_name)
                    self.tree.remove_command(cmd_name, guild=guild)
            
            print(f"   ✅ Removed {len(command_names)} commands internally")
            
            # 4. DOUBLE CHECK - Sync empty again to be sure
            print("4. Final verification sync...")
            await self.tree.sync()
            await self.tree.sync(guild=guild)
            print("   ✅ Final sync completed")
            
            print("\n" + "=" * 60)
            print("✅ NUCLEAR CLEANUP COMPLETE!")
            print("\n⚠️  IMPORTANT:")
            print("1. Wait 2-5 MINUTES before running main.py")
            print("2. Discord's cache can take time to clear")
            print("3. Check Discord developer portal if issues persist")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
            import traceback
            traceback.print_exc()
        
        await asyncio.sleep(5)  # Give time for final messages
        await self.close()
    
    async def on_ready(self):
        print(f'🧹 Cleanup Bot ready: {self.user}')
        print(f'🧹 Guilds: {len(self.guilds)}')

if __name__ == "__main__":
    bot = CleanupBot()
    bot.run(BOTTOKEN)