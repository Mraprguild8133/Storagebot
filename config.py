# -*- coding: utf-8 -*-
"""
Configuration file for the Telegram Subscription Bot
"""

# Bot token from @BotFather
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# API credentials (for handling large files >20MB)
# Get these from https://my.telegram.org/apps
API_ID = 123456  # Your API ID
API_HASH = "your_api_hash_here"

# Channel and Group IDs that users must join
# These can be usernames (with @) or numeric IDs (with - prefix for private channels/groups)
REQUIRED_CHANNEL_ID = "@your_channel_username"  # or "-1001234567890"
REQUIRED_GROUP_ID = "@your_group_username"      # or "-1001234567891"

# Log channel ID (optional, for logging new users)
LOG_CHANNEL_ID = None  # or "@your_log_channel" or "-1001234567892"

# Start message image URL (optional)
START_IMAGE_URL = "https://example.com/path/to/your/image.jpg"
