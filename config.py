# -*- coding: utf-8 -*-

"""
Configuration file for the Telegram Force Subscribe Bot.
Fill in your details here.
"""

# --- Telegram Bot API ---
# Get this token from @BotFather on Telegram.
BOT_TOKEN = "YOUR_BOT_TOKEN"

# --- Telegram Client API (for handling large files > 20MB) ---
# Optional: Get these from my.telegram.org.
API_ID = "YOUR_API_ID"
API_HASH = "YOUR_API_HASH"

# --- Bot Settings ---
# The channel and group the user must join.
# For public channels/groups, use the @username (e.g., "@my_channel").
# For private channels/groups, use the numerical chat ID (e.g., -1001234567890).
# The bot MUST be an admin in both with permission to invite users.
REQUIRED_CHANNEL_ID = "@your_channel_username"
REQUIRED_GROUP_ID = "@your_group_username"

# The private channel where the bot will send logs about new users.
# The bot MUST be an admin here with permission to post messages.
LOG_CHANNEL_ID = -1001234567890 # Must be a numerical ID

# --- Customization ---
# URL of the picture to send with the /start command.
# This should be a direct link to an image.
START_IMAGE_URL = "https://placehold.co/1280x720/6366f1/white?text=Welcome!"
