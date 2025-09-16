# -*- coding: utf-8 -*-
"""
A Telegram bot that shortens URLs using the TinyURL service.

This bot does the following:
1.  Responds to the /start command with a welcome message.
2.  Responds to the /help command with instructions.
3.  Receives a message from a user.
4.  Checks if the message is a valid URL.
5.  If it's a URL, it uses the TinyURL API to shorten it.
6.  Sends the shortened URL back to the user.
7.  If it's not a URL, it informs the user to send a valid one.

To use this bot:
1.  Install the required libraries:
    pip install python-telegram-bot==13.7 requests
2.  Get a bot token from @BotFather on Telegram.
3.  Replace 'YOUR_TELEGRAM_BOT_TOKEN' in this script with your actual token.
4.  Run the script: python url_shortener_bot.py
"""

import logging
import requests
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- Configuration ---
# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with the token you get from @BotFather
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# The base API URL for the URL shortening service. TinyURL is simple and requires no API key.
# You can swap this out with another service's API endpoint.
SHORTENER_API_URL = "http://tinyurl.com/api-create.php"

# --- Bot Setup ---

# Enable logging to see errors and bot activity
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Command Handlers ---

def start_command(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    welcome_message = (
        f"👋 *Welcome, {user.first_name}!* \n\n"
        "I am your friendly URL Shortener Bot. Just send me any long URL, and I will shorten it for you instantly.\n\n"
        "Features:\n"
        "✅ Simple to use\n"
        "✅ Fast and reliable\n"
        "✅ No API keys needed from you\n\n"
        "Type /help to see all available commands."
    )
    update.message.reply_html(welcome_message)


def help_command(update: Update, context: CallbackContext) -> None:
    """Sends a help message with instructions when the /help command is issued."""
    help_text = (
        "ℹ️ *How to Use Me*\n\n"
        "1.  **Send a URL:** Simply paste or type a long URL into the chat and send it.\n"
        "    *Example:* `https://www.google.com/search?q=very+long+search+query`\n\n"
        "2.  **Get a Short URL:** I will reply with a shortened URL from TinyURL.\n"
        "    *Example:* `https://tinyurl.com/2p998z7j`\n\n"
        "*Available Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message"
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# --- Message Handler ---

def shorten_url(update: Update, context: CallbackContext) -> None:
    """Shortens the URL sent by the user."""
    original_url = update.message.text
    chat_id = update.message.chat_id
    
    # Simple validation to check if the message looks like a URL
    if not (original_url.startswith('http://') or original_url.startswith('https://')):
        update.message.reply_text("❌ That doesn't look like a valid URL. Please send a link starting with `http://` or `https://`.", parse_mode=ParseMode.MARKDOWN)
        return

    # Inform the user that the process has started
    processing_message = context.bot.send_message(chat_id, "⚙️ Shortening your URL, please wait...")

    try:
        # Prepare parameters for the API request
        params = {'url': original_url}
        
        # Make the GET request to the shortening service API
        response = requests.get(SHORTENER_API_URL, params=params)
        
        # Check if the request was successful
        if response.status_code == 200:
            short_url = response.text
            message = (
                f"✅ *Success! Here is your short URL:*\n\n"
                f"`{short_url}`\n\n"
                f"🔗 *Original URL:*\n`{original_url}`"
            )
            context.bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=message, parse_mode=ParseMode.MARKDOWN)
        else:
            # Handle API errors
            error_message = f"⚠️ Sorry, I couldn't shorten that URL. The service returned an error (Status code: {response.status_code}). Please try again later."
            context.bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=error_message)

    except requests.RequestException as e:
        # Handle network or connection errors
        logger.error(f"Network error when shortening URL: {e}")
        error_message = "🆘 Oops! A network error occurred. I couldn't connect to the URL shortening service. Please check your connection or try again later."
        context.bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=error_message)
    except Exception as e:
        # Handle any other unexpected errors
        logger.error(f"An unexpected error occurred: {e}")
        error_message = "💥 An unexpected error occurred. Please try again."
        context.bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=error_message)


# --- Error Handler ---

def error_handler(update: Update, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')


# --- Main Bot Execution ---

def main() -> None:
    """Start the bot and listen for commands and messages."""
    
    # Create the Updater and pass it your bot's token.
    updater = Updater(TELEGRAM_TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register command handlers
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Register a message handler to process URLs
    # It filters for text messages that are not commands
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, shorten_url))
    
    # Register the error handler
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()
    logger.info("Bot has started successfully!")

    # Run the bot until you press Ctrl-C
    updater.idle()
    logger.info("Bot has been stopped.")


if __name__ == '__main__':
    main()
