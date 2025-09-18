# -*- coding: utf-8 -*-

"""
An advanced Telegram bot that forces users to subscribe to a channel and group
before they can use its features.

Features:
- Force subscription to a specified channel and group.
- Welcome message with a start picture and user's name.
- Inline keyboard for easy joining and verification.
- Stores new user data in a private log channel.
- Differentiates file handling for small and large files (conceptual).
- High-performance asynchronous design using python-telegram-bot v20+.
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# --- Configuration ---
# Replace these with your actual credentials and IDs.

# Get this from @BotFather on Telegram.
BOT_TOKEN = "YOUR_BOT_TOKEN" 

# These are for handling large files (optional, requires a user account).
# Get them from my.telegram.org.
API_ID = "YOUR_API_ID"
API_HASH = "YOUR_API_HASH"

# Your channel's and group's public username or private ID (e.g., -1001234567890).
# The bot MUST be an admin in both the channel and the group to check membership.
REQUIRED_CHANNEL_ID = "@your_channel_username"  # Or e.g., -1001234567890
REQUIRED_GROUP_ID = "@your_group_username"      # Or e.g., -1009876543210

# A private channel where the bot will store logs of new users.
# The bot MUST be an admin here to send messages.
LOG_CHANNEL_ID = -1001234567890 # Example private channel ID

# URL of the picture to send with the /start command.
START_IMAGE_URL = "https://placehold.co/1280x720/6366f1/white?text=Welcome!"

# --- End of Configuration ---


# Set up logging to see errors
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def is_user_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Checks if a user is a member of the required channel and group.
    Returns True if the user is subscribed to both, otherwise False.
    """
    if not REQUIRED_CHANNEL_ID or not REQUIRED_GROUP_ID:
        # If no channel/group is set, bypass the check.
        return True
        
    try:
        # Check channel membership
        channel_member = await context.bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL_ID, user_id=user_id
        )
        if channel_member.status not in ["member", "administrator", "creator"]:
            logger.info(f"User {user_id} is not in the channel.")
            return False

        # Check group membership
        group_member = await context.bot.get_chat_member(
            chat_id=REQUIRED_GROUP_ID, user_id=user_id
        )
        if group_member.status not in ["member", "administrator", "creator"]:
            logger.info(f"User {user_id} is not in the group.")
            return False

        logger.info(f"User {user_id} is subscribed to both channel and group.")
        return True
    except TelegramError as e:
        logger.error(f"Error checking subscription for user {user_id}: {e}")
        # If the bot is not an admin or the chat ID is wrong, it will fail.
        # Assume not subscribed on error to be safe.
        return False


def get_join_keyboard() -> InlineKeyboardMarkup:
    """Returns the inline keyboard with join links and a verification button."""
    channel_url = f"https://t.me/{str(REQUIRED_CHANNEL_ID).replace('@', '')}"
    group_url = f"https://t.me/{str(REQUIRED_GROUP_ID).replace('@', '')}"
    
    keyboard = [
        [InlineKeyboardButton("➡️ Join Our Channel ⬅️", url=channel_url)],
        [InlineKeyboardButton("➡️ Join Our Group ⬅️", url=group_url)],
        [InlineKeyboardButton("✅ I Have Joined ✅", callback_data="check_join")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def log_new_user(user, context: ContextTypes.DEFAULT_TYPE):
    """Sends a formatted message with new user details to the log channel."""
    if not LOG_CHANNEL_ID:
        return
        
    text = (
        f"**✨ New User Alert ✨**\n\n"
        f"**User ID:** `{user.id}`\n"
        f"**First Name:** {user.first_name}\n"
        f"**Last Name:** {user.last_name or 'N/A'}\n"
        f"**Username:** @{user.username or 'N/A'}"
    )
    try:
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID, text=text, parse_mode="Markdown"
        )
    except TelegramError as e:
        logger.error(f"Failed to send log message: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    
    # Log the user info, but only if they are new.
    if not context.user_data.get("is_old_user"):
        await log_new_user(user, context)
        context.user_data["is_old_user"] = True

    if await is_user_subscribed(user.id, context):
        welcome_text = f"🎉 Welcome back, {user.first_name}!\n\nYou're all set. You can now send me files."
        await update.message.reply_text(welcome_text)
    else:
        caption = (
            f"👋 **Welcome, {user.first_name}!**\n\n"
            "Before you can use this bot, you need to join our official channel and support group.\n\n"
            "1️⃣ Join the Channel.\n"
            "2️⃣ Join the Group.\n"
            "3️⃣ Click the 'I Have Joined' button below."
        )
        try:
            await update.message.reply_photo(
                photo=START_IMAGE_URL,
                caption=caption,
                reply_markup=get_join_keyboard(),
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.error(f"Error sending start photo: {e}. Sending text instead.")
            await update.message.reply_text(
                caption,
                reply_markup=get_join_keyboard(),
                parse_mode="Markdown",
            )


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    if query.data == "check_join":
        user_id = query.from_user.id
        if await is_user_subscribed(user_id, context):
            success_text = "✅ **Verification Successful!**\n\nThank you for joining! You can now use the bot.\n\nSend me any file to get started."
            await query.edit_message_caption(caption=success_text, parse_mode="Markdown")
        else:
            await context.bot.answer_callback_query(
                callback_query_id=query.id,
                text="❌ You haven't joined our channel and group yet. Please join both and try again.",
                show_alert=True,
            )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming files, checking for subscription first."""
    user = update.effective_user
    if not await is_user_subscribed(user.id, context):
        await update.message.reply_text(
            "⚠️ **Access Denied**\n\nPlease join our channel and group first to use this feature.",
            reply_markup=get_join_keyboard(),
            parse_mode="Markdown"
        )
        return

    message = update.message
    # Determine the file type and get the file object
    file = message.document or message.video or message.audio or message.photo[-1]
    
    if not file:
        await message.reply_text("I couldn't identify the file you sent. Please try again.")
        return
        
    file_size_mb = file.file_size / (1024 * 1024)
    
    await message.reply_text(f"Received your file! Size: {file_size_mb:.2f} MB.")

    # --- Logic for Small vs. Large Files ---
    # Telegram bots can download files up to 20 MB.
    # For files larger than that, you must use a user client (e.g., Pyrogram/Telethon)
    # with your API_ID and API_HASH.
    
    if file_size_mb <= 20:
        # Handle small files directly with the bot
        await message.reply_text("This is a small file. I can process it directly.")
        # Example: Echoing the file back to the user
        try:
            if message.document:
                await message.reply_document(document=file.file_id)
            elif message.video:
                await message.reply_video(video=file.file_id)
            # Add other file types as needed
        except TelegramError as e:
            logger.error(f"Error echoing small file: {e}")
            await message.reply_text("Sorry, I had trouble processing that file.")
            
    else:
        # Handle large files
        await message.reply_text(
            "This is a large file (>20 MB).\n"
            "**Note for Admin:** To handle this, the bot would need to use the Telegram Client API "
            "(with API_ID and API_HASH) to download and re-upload it. This part is for demonstration."
        )
        # In a real-world scenario, you would integrate a library like Pyrogram here.
        #
        # Example pseudo-code for Pyrogram integration:
        #
        # from pyrogram import Client
        # app = Client("my_account", api_id=API_ID, api_hash=API_HASH)
        # async with app:
        #     await message.reply_text("Downloading large file via user client...")
        #     file_path = await app.download_media(message)
        #     await message.reply_text("Uploading large file...")
        #     await app.send_document("me", file_path)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set. Please add it to the configuration.")

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()
    
    # --- Register Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    
    # This handler catches any message that contains a document, audio, video, or photo
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.PHOTO,
        file_handler
    ))
    
    # Register the error handler
    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
