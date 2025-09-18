# -*- coding: utf-8 -*-

"""
An advanced Telegram bot that forces users to subscribe to a channel and group
before they can use its features.
"""

import logging
import asyncio
import config  # Import the configuration file
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError, BadRequest

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
    if not config.REQUIRED_CHANNEL_ID or not config.REQUIRED_GROUP_ID:
        # If no channel/group is set, bypass the check.
        return True
        
    try:
        # Check both memberships concurrently for better performance
        channel_check = context.bot.get_chat_member(
            chat_id=config.REQUIRED_CHANNEL_ID, user_id=user_id
        )
        group_check = context.bot.get_chat_member(
            chat_id=config.REQUIRED_GROUP_ID, user_id=user_id
        )
        
        channel_member, group_member = await asyncio.gather(
            channel_check, group_check, 
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(channel_member, Exception):
            logger.error(f"Channel check failed for user {user_id}: {channel_member}")
            return False
        if isinstance(group_member, Exception):
            logger.error(f"Group check failed for user {user_id}: {group_member}")
            return False
            
        return (channel_member.status in ["member", "administrator", "creator"] and 
                group_member.status in ["member", "administrator", "creator"])
                
    except Exception as e:
        logger.error(f"Unexpected error checking subscription for user {user_id}: {e}")
        return False


def get_join_keyboard() -> InlineKeyboardMarkup:
    """Returns the inline keyboard with join links and a verification button."""
    # Handle both username-based and ID-based channel/group references
    if str(config.REQUIRED_CHANNEL_ID).startswith('@'):
        channel_url = f"https://t.me/{config.REQUIRED_CHANNEL_ID[1:]}"
    else:
        channel_url = f"https://t.me/c/{str(config.REQUIRED_CHANNEL_ID).replace('-100', '')}"
    
    if str(config.REQUIRED_GROUP_ID).startswith('@'):
        group_url = f"https://t.me/{config.REQUIRED_GROUP_ID[1:]}"
    else:
        group_url = f"https://t.me/c/{str(config.REQUIRED_GROUP_ID).replace('-100', '')}"
    
    keyboard = [
        [InlineKeyboardButton("➡️ Join Our Channel ⬅️", url=channel_url)],
        [InlineKeyboardButton("➡️ Join Our Group ⬅️", url=group_url)],
        [InlineKeyboardButton("✅ I Have Joined ✅", callback_data="check_join")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def log_new_user(user, context: ContextTypes.DEFAULT_TYPE):
    """Sends a formatted message with new user details to the log channel."""
    if not config.LOG_CHANNEL_ID:
        return
        
    text = (
        f"✨ New User Alert ✨\n\n"
        f"User ID: {user.id}\n"
        f"First Name: {user.first_name}\n"
        f"Last Name: {user.last_name or 'N/A'}\n"
        f"Username: @{user.username or 'N/A'}"
    )
    try:
        await context.bot.send_message(
            chat_id=config.LOG_CHANNEL_ID, text=text
        )
    except TelegramError as e:
        logger.error(f"Failed to send log message: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username or 'no-username'}) started the bot.")
    
    # Log the user info, but only if they are new.
    if not context.user_data.get("is_old_user"):
        await log_new_user(user, context)
        context.user_data["is_old_user"] = True

    if await is_user_subscribed(user.id, context):
        welcome_text = f"🎉 Welcome back, {user.first_name}!\n\nYou're all set. You can now send me files."
        await update.message.reply_text(welcome_text)
    else:
        caption = (
            f"👋 Welcome, {user.first_name}!\n\n"
            "Before you can use this bot, you need to join our official channel and support group.\n\n"
            "1️⃣ Join the Channel.\n"
            "2️⃣ Join the Group.\n"
            "3️⃣ Click the 'I Have Joined' button below."
        )
        try:
            # Try to send with photo if URL is provided
            if hasattr(config, 'START_IMAGE_URL') and config.START_IMAGE_URL:
                await update.message.reply_photo(
                    photo=config.START_IMAGE_URL,
                    caption=caption,
                    reply_markup=get_join_keyboard(),
                )
            else:
                await update.message.reply_text(
                    caption,
                    reply_markup=get_join_keyboard(),
                )
        except (TelegramError, BadRequest) as e:
            logger.error(f"Error sending start photo: {e}. Sending text instead.")
            await update.message.reply_text(
                caption,
                reply_markup=get_join_keyboard(),
            )


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    if query.data == "check_join":
        user_id = query.from_user.id
        if await is_user_subscribed(user_id, context):
            success_text = "✅ Verification Successful!\n\nThank you for joining! You can now use the bot.\n\nSend me any file to get started."
            try:
                await query.edit_message_caption(caption=success_text)
            except BadRequest:
                # If the message doesn't have a caption (text message instead of photo)
                await query.edit_message_text(text=success_text)
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
            "⚠️ Access Denied\n\nPlease join our channel and group first to use this feature.",
            reply_markup=get_join_keyboard()
        )
        return

    message = update.message
    # Determine the file type and get the file object
    if message.document:
        file = message.document
    elif message.video:
        file = message.video
    elif message.audio:
        file = message.audio
    elif message.photo:
        file = message.photo[-1]  # Get the highest resolution photo
    else:
        await message.reply_text("I couldn't identify the file you sent. Please try again.")
        return
        
    file_size_mb = file.file_size / (1024 * 1024) if file.file_size else 0
    
    await message.reply_text(f"Received your file! Size: {file_size_mb:.2f} MB.")

    if file_size_mb <= 20:
        await message.reply_text("This is a small file. I can process it directly.")
        try:
            if message.document:
                await message.reply_document(document=file.file_id)
            elif message.video:
                await message.reply_video(video=file.file_id)
            elif message.audio:
                await message.reply_audio(audio=file.file_id)
            elif message.photo:
                await message.reply_photo(photo=file.file_id)
        except TelegramError as e:
            logger.error(f"Error echoing file: {e}")
            await message.reply_text("Sorry, I had trouble processing that file.")
    else:
        await message.reply_text(
            "This is a large file (>20 MB).\n"
            f"Note for Admin: To handle this, the bot needs a Telegram Client with API_ID: {config.API_ID}."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main() -> None:
    """Start the bot."""
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise ValueError("BOT_TOKEN is not set in config.py. Please add it.")

    # Create the Application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.PHOTO,
        file_handler
    ))
    application.add_error_handler(error_handler)

    logger.info("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
