# Discord Content Tracker & Management Bot 🚀

A powerful, feature-rich Discord bot for tracking content creators, managing voice channels, reaction roles, and more - all with an intuitive interface and no paywalls!

## ✨ Features

### **🎥 Content Creator Tracking**
### **🔊 Join-to-Create Voice Channels**
### **🎭 Reaction Roles**
### **🛠️ Platform Integration**
### **📚 Comprehensive Help System**


## 📋 Installation

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- A MongoDB database (e.g. a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster)
- YouTube Data API v3 Key (for YouTube features)
- Twitch Client ID & Secret (for Twitch features)

### Step-by-Step Setup

1. **Clone the Repository**
```bash
git clone https://github.com/yourusername/discord-content-tracker.git
cd discord-content-tracker
```

2. **Install Dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure API Keys**
Create an `apikeys.env` file in the root directory:
```env
BOTTOKEN=your_discord_bot_token_here
SERVERID=your_server_id_here
MONGO_URI=mongodb+srv://<username>:<db_password>@your-cluster.mongodb.net/?retryWrites=true&w=majority
MONGO_PASSWORD=your_mongodb_password_here
```
- `MONGO_URI` is the connection string from your MongoDB provider. If it contains the literal `<db_password>` placeholder, `db.py` will substitute in `MONGO_PASSWORD` automatically.
- `MONGO_PASSWORD` can be omitted if your `MONGO_URI` already has the real password baked in.
- All of these values can also be set as real environment variables instead (useful for hosting platforms like Railway/Heroku) — the environment always takes precedence over `apikeys.env`.

4. **Set Up File Structure**
```
discord-bot/
├── cogs/
│   ├── platforms/
│   │   ├── youtube.py
│   │   └── twitch.py
│   ├── voice.py
│   ├── help.py
│   ├── reaction-role.py
│   ├── creator-videos.py
│   └── platform_setup.py
├── db.py           # Shared MongoDB connection/helpers
├── main.py
├── requirements.txt
└── apikeys.env     # Your API keys & MongoDB credentials
```

5. **Invite the Bot to Your Server**
Use the Discord Developer Portal to generate an invite link with these permissions:
- `Manage Roles` - auto-role assignment (creator follows, reaction roles, verification)
- `Manage Channels` - creating/editing/deleting temporary voice channels
- `Move Members` - moving users into and out of their temporary voice channel
- `Send Messages` - responding to commands and posting notifications
- `Embed Links` - voice control panels and other embeds
- `Add Reactions` - setting up reaction role messages
- `Read Message History` - finding/editing existing reaction-role messages
- `View Channel` and `Connect` (Voice) - seeing and joining the "Join to Create" channel
- `Use Application Commands` - slash commands

> ⚠️ **Role hierarchy matters:** the bot's own role must be positioned **above** any role it will assign (reaction roles, follow roles, etc.), or Discord will silently block the assignment even with `Manage Roles` granted.

## 🚀 Getting Started

### First Time Setup
1. Run the bot:
```bash
python main.py
```

2. Wait for the bot to fully start (you'll see "Logged in as..." in console)

## 🔧 Platform Configuration

### **YouTube Setup**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable "YouTube Data API v3"
4. Create credentials (API key)
5. Use in Discord: `/platforms`

### **Twitch Setup**
1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Register your application
3. Get Client ID and Client Secret
4. Use in Discord: `/platforms`

**More Platforms Soon!**

## ⚙️ Troubleshooting

### **Common Issues & Solutions**

#### **Bot Won't Start / MongoDB Errors**
- `❌ MONGO_URI is not set`: add `MONGO_URI` to `apikeys.env` or your environment.
- `❌ MONGO_PASSWORD is not set`: your `MONGO_URI` still contains the `<db_password>` placeholder, so `MONGO_PASSWORD` must also be set.
- `Could not connect to MongoDB`: double-check your cluster's IP allowlist (Atlas requires whitelisting the host running the bot, or `0.0.0.0/0` for testing) and that the username/password are correct.

#### **Voice Channels Not Working**
- Ensure bot has "Manage Channels" permission
- Check if "Join to Create" channel exists
- Verify bot has "Connect" permission in voice channels

#### **Reaction Roles Not Assigning**
- Bot needs "Manage Roles" permission
- Bot's role must be above the roles it's assigning
- Check role hierarchy in server settings

#### **Platform Tracking Not Working**
- Verify API keys are correct
- Check if platform is configured: `/list_platforms`
- Ensure bot has permission to send messages in target channel

### **Data Storage & Backups**
All bot data is stored in MongoDB (see `db.py`) instead of local JSON files. Each cog gets its own collection in the `HarpocratesDB` database, with a single `_id: "config"` document holding that cog's data:
- `reaction-role` collection - Reaction role configurations
- `creator-videos` collection - Creator tracking data
- `voice` collection - Voice channel configurations
- `platform_setup` collection - Platform API configurations

**IMPORTANT!** These collections/documents are created automatically the first time each cog saves data. To back up your bot's data, use your MongoDB provider's export/dump tools (e.g. `mongodump`, or Atlas's built-in backup features) against the `HarpocratesDB` database.

## 🚨 Advanced Usage

### **Customizing Help Categories**
Edit `help.py` to modify:
- Category emojis (`get_category_emoji`)
- Category descriptions (`get_category_description`)
- Command organization (`get_command_categories`)

### **Adding New Platforms**
1. Create a new platform class in `cogs/platforms/`
2. Inherit from `BasePlatform`
3. Implement required methods
4. Register in `main.py`

### **Custom Reaction Role Types**
The bot supports three message types:
- **Normal**: Standard reaction roles
- **Unique**: One reaction per user
- **Verify**: Auto-remove reaction after role assignment

## 🤝 Contributing

We welcome contributions! This bot is 100% free and open-source.

### **Ways to Contribute**
1. **Report Bugs**: Open an issue with detailed information
2. **Suggest Features**: What would make this bot better?
3. **Code Contributions**: Pull requests are welcome
4. **Documentation**: Help improve this README

### **Support the Project**
This bot is completely free to use. If you find it valuable and want to support development:

**PayPal**: [Soon]


No payment is required - this is our gift to the Discord community! All features are unlocked and freely available.

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🎯 Pro Tips

1. **Use Categories**: Organize your voice channels in categories for better management
2. **Role Hierarchy**: Place the bot's role near the top of your role list
3. **Channel Permissions**: Set up specific channels for different types of notifications
4. **Backup**: Regularly backup your `data/` folder
5. **Testing**: Test commands in a private channel first

## ❤️ Final Notes

This bot was created to provide premium features for free. We believe that good Discord tools should be accessible to everyone, regardless of budget. Enjoy the features, customize as needed, and most importantly - have fun building your community!

---

**Need Help?** Use `/help` in Discord or check the GitHub issues for common solutions.

**Found a Bug?** Please report it so we can fix it for everyone!

**Have an Idea?** We'd love to hear it! Feature requests are always welcome.

Happy tracking! 🚀
