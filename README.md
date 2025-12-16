# Discord Content Tracker & Management Bot 🚀

A powerful, feature-rich Discord bot for tracking content creators, managing voice channels, reaction roles, and more - all with an intuitive interface and no paywalls!

## ✨ Features

### **🎥 Content Creator Tracking**
- **YouTube & Twitch Support**: Get notified when creators upload new content or go live
- **Auto-Role Assignment**: Automatically assign roles to users who follow specific creators
- **Multi-Channel Support**: Send notifications to different channels for different creators
- **Manual Checking**: Instantly check and post the latest content from any creator

### **🔊 Smart Voice Channels**
- **Join-to-Create System**: Join a designated channel to create your own temporary voice channel
- **Dynamic Naming**: Auto-name channels based on your current game/activity
- **Custom Controls**: Rename, lock/unlock, set user limits, and manage permissions
- **Auto-Cleanup**: Empty channels are automatically deleted

### **🎭 Reaction Roles**
- **Easy Setup**: Create reaction role messages with a single command
- **Multiple Types**: Normal, Unique, and Verification message types
- **Role Management**: Add, remove, and edit roles easily
- **Persistent**: Roles survive bot restarts
- **Verification System**: Simple user verification through reactions

### **🛠️ Platform Integration**
- **Universal Setup**: Configure YouTube and Twitch with simple commands
- **API Management**: Securely store and manage platform credentials
- **Multi-Server Support**: Different configurations for different servers
- **Easy Removal**: Remove platform configurations when no longer needed

### **📚 Comprehensive Help System**
- **Category Organization**: Commands organized by functionality
- **Dropdown Interface**: Easy navigation through command categories
- **Detailed Descriptions**: Clear explanations for every command
- **Ephemeral Responses**: Private help to keep channels clean

## 📋 Installation

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
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
Create an `apikeys.py` file in the root directory:
```python
BOTTOKEN = "your_discord_bot_token_here"
SERVERID = your_server_id_here
```

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
├── data/           # Auto-created for config storage
├── main.py
├── nuclear_cleanup.py
├── requirements.txt
└── apikeys.py     # Your API keys
```

5. **Invite the Bot to Your Server**
Use the Discord Developer Portal to generate an invite link with these permissions:
- `Manage Roles`
- `Manage Channels`
- `Send Messages`
- `Read Messages`
- `Add Reactions`
- `Move Members`
- `Connect` (Voice)

## 🚀 Getting Started

### First Time Setup
1. Run the bot:
```bash
python main.py
```

2. Wait for the bot to fully start (you'll see "Logged in as..." in console)

3. Use these setup commands in your Discord server:

### **Essential Setup Commands**
| Command | Description | Usage |
|---------|-------------|-------|
| `/setup_platform` | Configure YouTube/Twitch | `/setup_platform platform:YouTube api_key:YOUR_API_KEY` |
| `/setup_vc` | Enable voice channel system | `/setup_vc editable:true` |
| `/role_create` | Create roles for reaction system | `/role_create name:Gamer color:#00FF00` |

## 📖 Command Reference

### **🎥 Creator Tracking Commands**
| Command | Description | Example |
|---------|-------------|---------|
| `/follow` | Start tracking a creator | `/follow creator:@pewdiepie platform:YouTube user:@user role:@Subscriber` |
| `/unfollow` | Stop tracking a creator | `/unfollow creator:pewdiepie platform:YouTube` |
| `/show_creators` | List all tracked creators | `/show_creators` |
| `/check_creator` | Manually check for new content | `/check_creator creator:shroud platform:Twitch` |

### **🔊 Voice Channel Commands**
| Command | Description | Example |
|---------|-------------|---------|
| `/setup_vc` | Enable temporary voice channels | `/setup_vc editable:true` |
| `/remove_vc` | Disable voice channel system | `/remove_vc` |

**Voice Channel Controls** (After joining a "Join to Create" channel):
- **Name**: Rename your channel
- **Status**: Set a status for your channel
- **User Limit**: Set maximum users
- **Gaming**: Auto-name based on your activity
- **Lock/Unlock**: Control who can join
- **Ghost/Unghost**: Hide/show your channel

### **🎭 Reaction Role Commands**
| Command | Description | Example |
|---------|-------------|---------|
| `/rr_create` | Create a reaction role message | `/rr_create title:"Get Roles" description:"React below\\nLine break example" message_type:Normal color:#FF0000` |
| `/rr_add` | Add role to a message | `/rr_add message_id:123456789 emoji:🎮 role:@Gamer` |
| `/rr_remove` | Remove role from message | `/rr_remove message_id:123456789 emoji:🎮` |
| `/rr_edit` | Edit an existing message | `/rr_edit message_id:123456789 title:"New Title"` |
| `/rr_delete` | Delete a reaction role | `/rr_delete message_id:123456789` |
| `/rr_list` | List all reaction roles | `/rr_list` |
| `/rr_info` | Get info about a message | `/rr_info message_id:123456789` |
| `/rr_cleanup` | Clean up invalid configs | `/rr_cleanup` |

### **🛠️ Utility Commands**
| Command | Description | Example |
|---------|-------------|---------|
| `/help` | Show all commands | `/help` |
| `/list_platforms` | Show configured platforms | `/list_platforms` |
| `/remove_platform` | Remove platform config | `/remove_platform platform:YouTube` |
| `/role_create` | Create a new role | `/role_create name:VIP color:#FFD700 hoist:true` |
| `/role_delete` | Delete a role | `/role_delete role:@VIP` |

## 🔧 Platform Configuration

### **YouTube Setup**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable "YouTube Data API v3"
4. Create credentials (API key)
5. Use in Discord: `/setup_platform platform:YouTube api_key:YOUR_API_KEY`

### **Twitch Setup**
1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Register your application
3. Get Client ID and Client Secret
4. Use in Discord: `/setup_platform platform:Twitch api_key:CLIENT_ID secret_key:CLIENT_SECRET`

**More Platforms Soon!**

## ⚙️ Troubleshooting

### **Common Issues & Solutions**

#### **Commands Not Showing Up**
```bash
# Run the nuclear cleanup script
python nuclear_cleanup.py
# Wait 2-5 minutes
python main.py
```

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

### **Data Files & Backups**
The bot stores data in the `data/` directory:
- `reaction_roles.json` - Reaction role configurations
- `tracked_channels.json` - Creator tracking data
- `voice_channels.json` - Voice channel configurations
- `platforms.json` - Platform API configurations

**IMPORTANT!** These files are create automatically.

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

**PayPal**: [Your PayPal Link Here]

No payment is required - this is our gift to the Discord community! All features are unlocked and freely available.

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔗 Links

- **GitHub Repository**: [Link to your repo]
- **Discord Support Server**: [Your server invite link]
- **Documentation**: [Link to detailed docs if available]

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