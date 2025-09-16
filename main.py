import os
import time
import math
import logging
import asyncio
from pyrogram import Client, filters, __version__ as pyrogram_version
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChannelInvalid, ChannelPrivate, ChatAdminRequired

# --- Configuration --- #
# Set up logging to see informational messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)

# Fetch environment variables
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
STORAGE_CHANNEL_ID_STR = os.environ.get("STORAGE_CHANNEL_ID")

# --- Environment Variable Validation --- #
if not all([API_ID, API_HASH, BOT_TOKEN, STORAGE_CHANNEL_ID_STR]):
    LOGGER.critical("CRITICAL ERROR: One or more environment variables are missing.")
    exit(1)

try:
    API_ID = int(API_ID)
except ValueError:
    LOGGER.critical("CRITICAL ERROR: API_ID is not a valid integer.")
    exit(1)

try:
    STORAGE_CHANNEL_ID = int(STORAGE_CHANNEL_ID_STR)
except ValueError:
    STORAGE_CHANNEL_ID = STORAGE_CHANNEL_ID_STR

# --- Utility Functions --- #
def human_readable_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

async def verify_storage_channel(client):
    """Verify the bot has access to the storage channel"""
    try:
        chat = await client.get_chat(STORAGE_CHANNEL_ID)
        LOGGER.info(f"Storage channel verified: {chat.title}")
        return True
    except (ChannelInvalid, ChannelPrivate, ChatAdminRequired) as e:
        LOGGER.error(f"Bot doesn't have access to storage channel: {e}")
        return False
    except Exception as e:
        LOGGER.error(f"Error verifying storage channel: {e}")
        return False

# --- Pyrogram Client Initialization --- #
app = Client(
    "file_storage_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=10,  # Reduced workers for stability
    sleep_threshold=60
)

# --- Progress Callback --- #
progress_updates = {}

async def progress_for_pyrogram(current, total, ud_type, message: Message, start_time):
    """Custom progress callback to show real-time status of uploads/downloads"""
    task_id = message.id
    now = time.time()

    # Update progress only once every 2 seconds to avoid flooding
    if task_id in progress_updates and (now - progress_updates[task_id]) < 2:
        return
    
    progress_updates[task_id] = now
    
    diff = now - start_time
    if diff == 0:
        diff = 0.001  # Avoid division by zero

    speed = current / diff
    percentage = current * 100 / total
    
    # Visual progress bar
    filled_blocks = math.floor(percentage / 10)
    progress_bar = "[{0}{1}]".format(
        ''.join(["⬢" for _ in range(filled_blocks)]),
        ''.join(["⬡" for _ in range(10 - filled_blocks)])
    )

    # Human-readable file sizes
    current_str = human_readable_size(current)
    total_str = human_readable_size(total)
    speed_str = f"{human_readable_size(speed)}/s"

    # ETA Calculation
    eta_seconds = (total - current) / speed if speed > 0 else 0
    eta = time.strftime("%H:%M:%S", time.gmtime(eta_seconds)) if eta_seconds > 0 else "00:00:00"

    progress_message = (
        f"**{ud_type}**\n"
        f"{progress_bar} {percentage:.2f}%\n"
        f"➢ **Done:** {current_str}\n"
        f"➢ **Size:** {total_str}\n"
        f"➢ **Speed:** {speed_str}\n"
        f"➢ **ETA:** {eta}"
    )

    try:
        await message.edit_text(progress_message)
    except FloodWait as e:
        LOGGER.warning(f"FloodWait: waiting for {e.x} seconds.")
        await asyncio.sleep(e.x)
    except Exception as e:
        LOGGER.warning(f"Failed to edit progress message: {e}")

# --- Bot Command Handlers --- #
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    """Handler for the /start command"""
    await message.reply_text(
        "👋 **Hello! I am your personal file storage assistant.**\n\n"
        "Send me any file, and I will upload it to our storage channel and give you a shareable link.\n\n"
        "**Features:**\n"
        "• Handles files up to 4GB\n"
        "• High-speed uploads and downloads\n"
        "• Real-time progress tracking\n\n"
        "Use /help for instructions or /status to check bot status."
    )

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message: Message):
    """Handler for the /help command"""
    await message.reply_text(
        "**How to use me:**\n\n"
        "1. Simply send me any file (document, video, audio, photo, voice, or video note)\n"
        "2. Wait for the upload to complete. I will show you the progress\n"
        "3. Once finished, I will provide you with a link to the file in the storage channel\n\n"
        "**Note:** Files larger than 4GB cannot be handled due to Telegram limitations."
    )

@app.on_message(filters.command("status") & filters.private)
async def status_command(client, message: Message):
    """Check bot status and storage channel accessibility"""
    try:
        chat = await client.get_chat(STORAGE_CHANNEL_ID)
        status = "✅ Connected" if chat else "❌ Not accessible"
        await message.reply_text(
            f"🤖 **Bot Status**\n\n"
            f"**Storage Channel:** {status}\n"
            f"**Channel Name:** {chat.title if chat else 'N/A'}\n"
            f"**Channel ID:** `{STORAGE_CHANNEL_ID}`\n"
            f"**Pyrogram Version:** {pyrogram_version}\n\n"
            f"*Send a file to test upload functionality.*"
        )
    except Exception as e:
        await message.reply_text(f"❌ **Error accessing storage channel:** {str(e)}")

# --- File Handling Logic --- #
@app.on_message(filters.private & (
    filters.document | filters.video | filters.audio
))
async def handle_file(client, message: Message):
    """Handler for incoming files"""
    media = message.document or message.video or message.audio
    
    if not media:
        await message.reply_text("Unsupported file type.")
        return

    # Get file info
    file_name = media.file_name or "Untitled"
    file_size = media.file_size

    # Telegram imposes a 4GB limit for bots
    if file_size and file_size > 4 * 1024 * 1024 * 1024:
        await message.reply_text("❌ **Error:** File size is larger than 4GB, which is not supported by Telegram.")
        return

    status_message = await message.reply_text("Initializing...", quote=True)
    start_time = time.time()
    downloaded_file_path = None
    
    try:
        # 1. Download the file from the user to the bot's server
        LOGGER.info(f"Starting download for: {file_name}")
        downloaded_file_path = await client.download_media(
            message=message,
            progress=progress_for_pyrogram,
            progress_args=("Downloading...", status_message, start_time)
        )
        LOGGER.info(f"File downloaded to: {downloaded_file_path}")

        # 2. Upload the file from the bot's server to the storage channel
        upload_start_time = time.time()
        LOGGER.info(f"Starting upload to channel {STORAGE_CHANNEL_ID} for: {file_name}")
        
        # Determine which function to use for sending based on file type
        if message.document:
            sent_message = await client.send_document(
                chat_id=STORAGE_CHANNEL_ID, 
                document=downloaded_file_path, 
                caption=f"`{file_name}`",
                progress=progress_for_pyrogram, 
                progress_args=("Uploading...", status_message, upload_start_time)
            )
        elif message.video:
            sent_message = await client.send_video(
                chat_id=STORAGE_CHANNEL_ID, 
                video=downloaded_file_path, 
                caption=f"`{file_name}`",
                progress=progress_for_pyrogram, 
                progress_args=("Uploading...", status_message, upload_start_time)
            )
        elif message.audio:
            sent_message = await client.send_audio(
                chat_id=STORAGE_CHANNEL_ID, 
                audio=downloaded_file_path, 
                caption=f"`{file_name}`",
                progress=progress_for_pyrogram, 
                progress_args=("Uploading...", status_message, upload_start_time)
            )
            
        LOGGER.info(f"File uploaded successfully: {file_name}")

        # 3. Generate the shareable link
        try:
            share_link = sent_message.link
        except Exception:
            share_link = "Private channel - use forward below"

        # 4. Send the final success message with the link
        success_text = (
            f"✅ **File Uploaded Successfully!**\n\n"
            f"**File Name:** `{file_name}`\n"
            f"**Size:** {human_readable_size(file_size) if file_size else 'N/A'}\n"
            f"**Type:** {type(media).__name__.capitalize()}\n"
            f"**Share Link:** {share_link}\n\n"
            f"*File ID:* `{sent_message.id}`"
        )
        await status_message.edit_text(success_text)

        # For private channels, forward the message to the user for easy access
        if not hasattr(sent_message, 'link') or not sent_message.link:
            await sent_message.forward(message.chat.id)

    except FloodWait as e:
        wait_time = e.x
        LOGGER.warning(f"FloodWait: Need to wait for {wait_time} seconds")
        await status_message.edit_text(f"⏳ **Too many requests!** Please wait for {wait_time} seconds and try again.")
        await asyncio.sleep(wait_time)
    except Exception as e:
        LOGGER.error(f"An error occurred while handling file '{file_name}': {e}", exc_info=True)
        await status_message.edit_text("❌ **Error:** An unexpected error occurred. Please try again later.")
    finally:
        # Clean up by deleting the downloaded file from the server
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            try:
                os.remove(downloaded_file_path)
                LOGGER.info(f"Cleaned up local file: {downloaded_file_path}")
            except Exception as e:
                LOGGER.error(f"Error deleting local file: {e}")
        # Clear the progress tracker for this task
        if 'status_message' in locals():
            progress_updates.pop(status_message.id, None)

# --- Main Execution --- #
async def main():
    """Starts the bot."""
    LOGGER.info("Starting the bot...")
    
    try:
        await app.start()
    except Exception as e:
        LOGGER.critical(f"Failed to start bot: {e}")
        return
    
    # Verify we can access the storage channel
    if not await verify_storage_channel(app):
        LOGGER.critical("Cannot access storage channel. Shutting down.")
        await app.stop()
        exit(1)
    
    user_bot = await app.get_me()
    LOGGER.info(f"Bot started as @{user_bot.username}")
    
    # Send a startup message to the logs
    try:
        await app.send_message(STORAGE_CHANNEL_ID, "🤖 File Storage Bot is now online!")
    except Exception as e:
        LOGGER.warning(f"Could not send startup message: {e}")
    
    # Keep the bot running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped manually.")
    except Exception as e:
        LOGGER.error(f"Unexpected error in main loop: {e}")
    finally:
        await app.stop()
        LOGGER.info("Bot stopped successfully.")

if __name__ == "__main__":
    # Check if we're running in an environment with all required variables
    LOGGER.info("Checking environment variables...")
    for var in ["API_ID", "API_HASH", "BOT_TOKEN", "STORAGE_CHANNEL_ID"]:
        value = os.environ.get(var)
        LOGGER.info(f"{var}: {'Set' if value else 'Missing'}")
    
    # Run the bot
    asyncio.run(main())
