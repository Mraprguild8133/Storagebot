import os
import time
import math
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
import asyncio

# --- Configuration --- #
# Set up logging to see informational messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

# Fetch environment variables
# To get these, go to my.telegram.org
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
# Get this from @BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# This is the ID of the channel where files will be stored.
# Make sure your bot is an admin in this channel.
# It can be a public channel username (@channel_name) or a private channel ID (e.g., -1001234567890).
STORAGE_CHANNEL_ID_STR = os.environ.get("STORAGE_CHANNEL_ID")

# --- Environment Variable Validation --- #
if not all([API_ID, API_HASH, BOT_TOKEN, STORAGE_CHANNEL_ID_STR]):
    LOGGER.critical("CRITICAL ERROR: One or more environment variables (API_ID, API_HASH, BOT_TOKEN, STORAGE_CHANNEL_ID) are missing.")
    exit(1) # Exit if essential config is missing

try:
    API_ID = int(API_ID)
except ValueError:
    LOGGER.critical("CRITICAL ERROR: API_ID is not a valid integer.")
    exit(1)

try:
    STORAGE_CHANNEL_ID = int(STORAGE_CHANNEL_ID_STR)
except ValueError:
    # If it's not an integer, assume it's a public channel username like @channelname
    STORAGE_CHANNEL_ID = STORAGE_CHANNEL_ID_STR


# --- Pyrogram Client Initialization --- #
# Create a new Pyrogram client
# The "bot" name is the session file name.
app = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=20 # Number of concurrent workers for handling updates
)

# --- Progress Callback --- #
# A dictionary to keep track of the last update time for each task
progress_updates = {}

async def progress_for_pyrogram(current, total, ud_type, message: Message, start_time):
    """
    Custom progress callback to show real-time status of uploads/downloads.
    """
    task_id = message.id
    now = time.time()

    # Update progress only once every 2 seconds to avoid flooding Telegram's API
    if task_id in progress_updates and (now - progress_updates[task_id]) < 2:
        return
    
    progress_updates[task_id] = now
    
    diff = now - start_time
    if diff == 0:
        diff = 0.001 # Avoid division by zero

    speed = current / diff
    percentage = current * 100 / total
    
    # Visual progress bar
    progress_bar = "[{0}{1}]".format(
        ''.join(["⬢" for i in range(math.floor(percentage / 10))]),
        ''.join(["⬡" for i in range(10 - math.floor(percentage / 10))])
    )

    # Human-readable file sizes
    current_str = f"{current / (1024 * 1024):.2f} MB"
    total_str = f"{total / (1024 * 1024):.2f} MB"
    speed_str = f"{speed / 1024 / 1024:.2f} MB/s"

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
        # Edit the status message to show the new progress
        await message.edit_text(progress_message)
    except FloodWait as e:
        # If we are rate-limited, wait for the specified duration
        LOGGER.warning(f"FloodWait: waiting for {e.x} seconds.")
        await asyncio.sleep(e.x)
    except Exception as e:
        # Log other errors if the message couldn't be edited
        LOGGER.warning(f"Failed to edit progress message: {e}")


# --- Bot Command Handlers --- #
@app.on_message(filters.command("start") & filters.private)
async def start_command(_, message: Message):
    """
    Handler for the /start command. Greets the user.
    """
    await message.reply_text(
        "👋 **Hello! I am your personal file storage assistant.**\n\n"
        "Send me any file, and I will upload it to our storage channel and give you a shareable link.\n\n"
        "**Features:**\n"
        "• Handles files up to 4GB.\n"
        "• High-speed uploads and downloads.\n"
        "• Real-time progress tracking."
    )

@app.on_message(filters.command("help") & filters.private)
async def help_command(_, message: Message):
    """
    Handler for the /help command. Provides instructions.
    """
    await message.reply_text(
        "**How to use me:**\n\n"
        "1. Simply send me any file (document, video, or audio).\n"
        "2. Wait for the upload to complete. I will show you the progress.\n"
        "3. Once finished, I will provide you with a link to the file in the storage channel."
    )


# --- File Handling Logic --- #
@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(_, message: Message):
    """
    Handler for incoming files (documents, videos, audio).
    Downloads from the user and uploads to the storage channel.
    """
    media = message.document or message.video or message.audio
    if not media:
        await message.reply_text("Unsupported file type.")
        return

    file_name = media.file_name or "Untitled"
    file_size = media.file_size
    
    # Telegram imposes a 4GB limit for bots on 64-bit systems.
    if file_size > 4 * 1024 * 1024 * 1024:
         await message.reply_text("❌ **Error:** File size is larger than 4GB, which is not supported by Telegram.")
         return

    status_message = await message.reply_text("Initializing...", quote=True)
    start_time = time.time()
    downloaded_file_path = None
    
    try:
        # 1. Download the file from the user to the bot's server
        LOGGER.info(f"Starting download for: {file_name}")
        downloaded_file_path = await app.download_media(
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
            sent_message = await app.send_document(
                chat_id=STORAGE_CHANNEL_ID, document=downloaded_file_path, caption=f"`{file_name}`",
                progress=progress_for_pyrogram, progress_args=("Uploading...", status_message, upload_start_time)
            )
        elif message.video:
             sent_message = await app.send_video(
                chat_id=STORAGE_CHANNEL_ID, video=downloaded_file_path, caption=f"`{file_name}`",
                progress=progress_for_pyrogram, progress_args=("Uploading...", status_message, upload_start_time)
            )
        else: # Audio
            sent_message = await app.send_audio(
                chat_id=STORAGE_CHANNEL_ID, audio=downloaded_file_path, caption=f"`{file_name}`",
                progress=progress_for_pyrogram, progress_args=("Uploading...", status_message, upload_start_time)
            )
        LOGGER.info(f"File uploaded successfully: {file_name}")

        # 3. Generate the shareable link
        share_link = sent_message.link if sent_message.link else "Private channel, direct forwarding is used."

        # 4. Send the final success message with the link
        success_text = (
            f"✅ **File Uploaded Successfully!**\n\n"
            f"**File Name:** `{file_name}`\n"
            f"**Share Link:** {share_link}"
        )
        await status_message.edit_text(success_text)

        # For private channels, forward the message to the user for easy access.
        if not sent_message.link:
            await sent_message.forward(message.chat.id)

    except Exception as e:
        LOGGER.error(f"An error occurred while handling file '{file_name}': {e}", exc_info=True)
        await status_message.edit_text("❌ **Error:** An unexpected error occurred. Please check the logs or try again later.")
    finally:
        # 5. Clean up by deleting the downloaded file from the server
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            os.remove(downloaded_file_path)
            LOGGER.info(f"Cleaned up local file: {downloaded_file_path}")
        # Clear the progress tracker for this task
        if 'status_message' in locals():
            progress_updates.pop(status_message.id, None)

# --- Main Execution --- #
async def main():
    """Starts the bot."""
    LOGGER.info("Starting the bot...")
    await app.start()
    user_bot = await app.get_me()
    LOGGER.info(f"Bot started as @{user_bot.username}")
    # Keep the bot running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped manually.")
    except Exception as e:
        LOGGER.critical(f"An unhandled exception occurred at the top level: {e}", exc_info=True)
