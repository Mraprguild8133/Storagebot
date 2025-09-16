# -*- coding: utf-8 -*-
"""
A Telegram bot that shortens URLs using multiple URL shortening services.
This script is updated to use python-telegram-bot v20+ and the asyncio library.

This bot does the following:
1.  Responds to the /start command with a welcome message.
2.  Responds to the /help command with instructions.
3.  Allows users to select a URL shortening service with /service command.
4.  Receives a message from a user.
5.  Checks if the message is a valid URL.
6.  Shortens the URL using the selected service.
7.  Sends the shortened URL back to the user.

To use this bot:
1.  Install the required libraries:
    pip install python-telegram-bot aiohttp
2.  Get a bot token from @BotFather on Telegram.
3.  Replace 'YOUR_TELEGRAM_BOT_TOKEN' with your actual token.
4.  Run the script: python modern_bot.py
"""

import logging
import aiohttp
import asyncio
from urllib.parse import urlparse, quote
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext

# --- Configuration ---
# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with the token you get from @BotFather
TELEGRAM_TOKEN = "8345094798:AAF69DkHwxNmHGZO8itDMsU_qcifncYxpVM"

# Supported URL shortening services
SERVICES = {
    'tinyurl': {
        'name': 'TinyURL',
        'api_url': 'http://tinyurl.com/api-create.php',
        'method': 'GET',
        'param': 'url'
    },
    'bitly': {
        'name': 'Bitly',
        'api_url': 'https://api-ssl.bitly.com/v4/shorten',
        'method': 'POST',
        'headers': {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer YOUR_BITLY_ACCESS_TOKEN'  # Replace with your Bitly access token
        },
        'json_key': 'link'
    },
    'isgd': {
        'name': 'is.gd',
        'api_url': 'https://is.gd/create.php',
        'method': 'GET',
        'params': {
            'format': 'json'
        },
        'param': 'url',
        'json_key': 'shorturl'
    },
    'vgd': {
        'name': 'v.gd',
        'api_url': 'https://v.gd/create.php',
        'method': 'GET',
        'params': {
            'format': 'json'
        },
        'param': 'url',
        'json_key': 'shorturl'
    },
    'cleanuri': {
        'name': 'CleanURI',
        'api_url': 'https://cleanuri.com/api/v1/shorten',
        'method': 'POST',
        'headers': {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        'param': 'url',
        'json_key': 'result_url'
    },
    'dagd': {
        'name': 'da.gd',
        'api_url': 'https://da.gd/shorten',
        'method': 'POST',
        'headers': {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        'param': 'url'
    }
}

# Default service
DEFAULT_SERVICE = 'tinyurl'

# --- Bot Setup ---

# Enable logging to see errors and bot activity
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    service_list = "\n".join([f"• {service['name']} ({key})" for key, service in SERVICES.items()])
    
    welcome_message = (
        f"👋 *Welcome, {user.first_name}!* \n\n"
        "I am your friendly URL Shortener Bot with support for multiple services. "
        "Just send me any long URL, and I will shorten it for you instantly.\n\n"
        f"*Currently using:* {SERVICES[context.user_data.get('service', DEFAULT_SERVICE)]['name']}\n\n"
        "*Available Services:*\n"
        f"{service_list}\n\n"
        "Use /service <name> to change the shortening service.\n"
        "Type /help to see all available commands."
    )
    await update.message.reply_text(welcome_message, parse_mode=constants.ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message with instructions when the /help command is issued."""
    service_list = "\n".join([f"• {service['name']} ({key})" for key, service in SERVICES.items()])
    
    help_text = (
        "ℹ️ *How to Use Me*\n\n"
        "1.  **Select a service** (optional): Use /service <name> to choose a URL shortening service.\n"
        "    *Available services:*\n"
        f"{service_list}\n\n"
        "2.  **Send a URL:** Simply paste or type a long URL into the chat and send it.\n"
        "    *Example:* `https://www.google.com/search?q=very+long+search+query`\n\n"
        "3.  **Get a Short URL:** I will reply with a shortened URL using your selected service.\n\n"
        "*Available Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/service <name> - Change URL shortening service"
    )
    await update.message.reply_text(help_text, parse_mode=constants.ParseMode.MARKDOWN)

async def service_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows users to change the URL shortening service."""
    if not context.args:
        current_service = context.user_data.get('service', DEFAULT_SERVICE)
        await update.message.reply_text(
            f"🛠 *Current service:* {SERVICES[current_service]['name']}\n\n"
            "To change service, use: /service <name>\n"
            "Available services:\n" + 
            "\n".join([f"• {service['name']} ({key})" for key, service in SERVICES.items()]),
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return
    
    service_name = context.args[0].lower()
    if service_name not in SERVICES:
        await update.message.reply_text(
            "❌ Invalid service name. Available services:\n" + 
            "\n".join([f"• {service['name']} ({key})" for key, service in SERVICES.items()])
        )
        return
    
    context.user_data['service'] = service_name
    await update.message.reply_text(
        f"✅ *Service changed to:* {SERVICES[service_name]['name']}",
        parse_mode=constants.ParseMode.MARKDOWN
    )

# --- URL Shortening Functions ---

async def shorten_with_tinyurl(url: str) -> str:
    """Shorten URL using TinyURL service."""
    async with aiohttp.ClientSession() as session:
        async with session.get(SERVICES['tinyurl']['api_url'], params={'url': url}) as response:
            if response.status == 200:
                return await response.text()
            else:
                raise Exception(f"TinyURL API error: {response.status}")

async def shorten_with_bitly(url: str) -> str:
    """Shorten URL using Bitly service."""
    # Note: You need to set up a Bitly account and get an access token
    headers = SERVICES['bitly']['headers'].copy()
    data = {'long_url': url}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            SERVICES['bitly']['api_url'], 
            headers=headers, 
            json=data
        ) as response:
            if response.status == 200:
                result = await response.json()
                return result['link']
            else:
                error = await response.text()
                raise Exception(f"Bitly API error: {response.status} - {error}")

async def shorten_with_isgd(url: str) -> str:
    """Shorten URL using is.gd service."""
    params = SERVICES['isgd']['params'].copy()
    params['url'] = url
    
    async with aiohttp.ClientSession() as session:
        async with session.get(SERVICES['isgd']['api_url'], params=params) as response:
            if response.status == 200:
                result = await response.json()
                return result[SERVICES['isgd']['json_key']]
            else:
                raise Exception(f"is.gd API error: {response.status}")

async def shorten_with_vgd(url: str) -> str:
    """Shorten URL using v.gd service."""
    params = SERVICES['vgd']['params'].copy()
    params['url'] = url
    
    async with aiohttp.ClientSession() as session:
        async with session.get(SERVICES['vgd']['api_url'], params=params) as response:
            if response.status == 200:
                result = await response.json()
                return result[SERVICES['vgd']['json_key']]
            else:
                raise Exception(f"v.gd API error: {response.status}")

async def shorten_with_cleanuri(url: str) -> str:
    """Shorten URL using CleanURI service."""
    data = {'url': url}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            SERVICES['cleanuri']['api_url'], 
            headers=SERVICES['cleanuri']['headers'],
            data=data
        ) as response:
            if response.status == 200:
                result = await response.json()
                return result[SERVICES['cleanuri']['json_key']]
            else:
                raise Exception(f"CleanURI API error: {response.status}")

async def shorten_with_dagd(url: str) -> str:
    """Shorten URL using da.gd service."""
    data = {'url': url}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            SERVICES['dagd']['api_url'], 
            headers=SERVICES['dagd']['headers'],
            data=data
        ) as response:
            if response.status == 200:
                return (await response.text()).strip()
            else:
                raise Exception(f"da.gd API error: {response.status}")

# Map service names to their respective functions
SERVICE_FUNCTIONS = {
    'tinyurl': shorten_with_tinyurl,
    'bitly': shorten_with_bitly,
    'isgd': shorten_with_isgd,
    'vgd': shorten_with_vgd,
    'cleanuri': shorten_with_cleanuri,
    'dagd': shorten_with_dagd
}

async def shorten_url(service: str, url: str) -> str:
    """Shorten URL using the specified service."""
    if service not in SERVICE_FUNCTIONS:
        raise ValueError(f"Unknown service: {service}")
    
    return await SERVICE_FUNCTIONS[service](url)

# --- Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shortens the URL sent by the user."""
    original_url = update.message.text.strip()
    
    # Simple validation to check if the message looks like a URL
    if not (original_url.startswith('http://') or original_url.startswith('https://')):
        await update.message.reply_text(
            "❌ That doesn't look like a valid URL. Please send a link starting with `http://` or `https://`.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    # Get the selected service or use default
    service_key = context.user_data.get('service', DEFAULT_SERVICE)
    service_name = SERVICES[service_key]['name']

    # Inform the user that the process has started
    processing_message = await update.message.reply_text(
        f"⚙️ Shortening your URL using {service_name}, please wait..."
    )

    try:
        # Shorten the URL
        short_url = await shorten_url(service_key, original_url)
        
        message = (
            f"✅ *Success! Here is your short URL:*\n\n"
            f"`{short_url}`\n\n"
            f"🔗 *Original URL:*\n`{original_url}`\n\n"
            f"🛠 *Service used:* {service_name}"
        )
        await processing_message.edit_text(message, parse_mode=constants.ParseMode.MARKDOWN)

    except Exception as e:
        # Handle any errors
        logger.error(f"Error shortening URL: {e}")
        error_message = (
            f"❌ Sorry, I couldn't shorten that URL using {service_name}. "
            "Please try again or use /service to select a different service."
        )
        await processing_message.edit_text(error_message)

# --- Main Bot Execution ---

def main() -> None:
    """Start the bot and listen for commands and messages."""
    
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("service", service_command))

    # Register a message handler to process URLs
    # It filters for text messages that are not commands
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the Bot
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot has been stopped.")


if __name__ == '__main__':
    main()
