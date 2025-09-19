# main.py
# A comprehensive Telegram file storage bot with Wasabi cloud integration.

import os
import time
import logging
import asyncio
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
)
from pyrogram.errors import FloodWait
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WASABI_ACCESS_KEY = os.getenv("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.getenv("WASABI_SECRET_KEY")
WASABI_BUCKET = os.getenv("WASABI_BUCKET")
WASABI_REGION = os.getenv("WASABI_REGION")

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)

# --- In-memory storage (replace with a database for production) ---
# This is a simple dictionary to store file metadata.
# A proper database like SQLite, PostgreSQL, or a NoSQL DB would be better.
file_db = {}
user_db = {} # Stores user-specific settings like channel_id

# --- Pyrogram Client Initialization ---
app = Client("file_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Wasabi S3 Client Initialization ---
try:
    s3_client = boto3.client(
        "s3",
        endpoint_url=f"https://s3.{WASABI_REGION}.wasabisys.com",
        aws_access_key_id=WASABI_ACCESS_KEY,
        aws_secret_access_key=WASABI_SECRET_KEY,
        region_name=WASABI_REGION,
    )
    LOGGER.info("Successfully connected to Wasabi.")
except (NoCredentialsError, PartialCredentialsError) as e:
    LOGGER.error(f"Wasabi credentials not found or incomplete: {e}")
    s3_client = None
except Exception as e:
    LOGGER.error(f"An unexpected error occurred during Wasabi connection: {e}")
    s3_client = None


# --- Helper Functions ---
def human_readable_size(size, decimal_places=2):
    """Converts size in bytes to a human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


progress_update_tracker = {}

async def progress_callback(current, total, message, action, start_time):
    """Updates the progress message during uploads/downloads."""
    key = (message.chat.id, message.id)
    now = time.time()

    # Rate limit updates to once every 2 seconds to avoid FloodWait
    if key in progress_update_tracker and now - progress_update_tracker.get(key, 0) < 2:
        return
    progress_update_tracker[key] = now
    
    try:
        percentage = current * 100 / total
        elapsed_time = now - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        progress_str = (
            f"{action}:\n"
            f"[{'●' * int(percentage / 10)}{'○' * (10 - int(percentage / 10))}] {percentage:.2f}%\n"
            f"{human_readable_size(current)} of {human_readable_size(total)}\n"
            f"Speed: {human_readable_size(speed)}/s\n"
        )
        await message.edit_text(progress_str)
    except FloodWait as e:
        await asyncio.sleep(e.x)
    except Exception:
        # Avoid crashing on message edit errors
        pass


# --- Bot Command Handlers ---
@app.on_message(filters.command("start"))
async def start_command(_, message: Message):
    """Handles the /start command."""
    start_text = (
        "👋 **Welcome to the File Storage & Streaming Bot!**\n\n"
        "I can help you upload, store, and stream files up to 4GB using Wasabi Cloud Storage.\n\n"
        "**Features:**\n"
        "- 📤 Upload files directly or by forwarding.\n"
        "- ☁️ Securely store files in Wasabi Cloud.\n"
        "- 🔗 Get direct download and streaming links.\n"
        "- ▶️ One-click streaming in MX Player & VLC.\n\n"
        "To get started, simply send me a file or use the /upload command. "
        "For a full list of commands, use /help."
    )
    await message.reply_text(start_text, quote=True)


@app.on_message(filters.command("help"))
async def help_command(_, message: Message):
    """Handles the /help command."""
    help_text = (
        "**🤖 Bot Commands Guide**\n\n"
        "`/start` - Shows the welcome message.\n"
        "`/upload` - Upload a file (or just send any file).\n"
        "`/list` - List your stored files.\n"
        "`/download <file_id>` - Get download link for a file.\n"
        "`/stream <file_id>` - Get streaming link for a file.\n"
        "`/web <file_id>` - Get a web player link for a file.\n"
        "`/setchannel <channel_id>` - Set a channel for file backups.\n"
        "`/test` - Check the connection to Wasabi Cloud.\n"
        "`/help` - Shows this help message."
    )
    await message.reply_text(help_text, quote=True)

class S3Progress:
    """A class to track S3 upload progress and report it via a callback."""
    def __init__(self, message, total_size, action, start_time):
        self._message = message
        self._total_size = total_size
        self._action = action
        self._start_time = start_time
        self._seen_so_far = 0
        self._loop = asyncio.get_event_loop()

    def __call__(self, bytes_amount):
        self._seen_so_far += bytes_amount
        asyncio.run_coroutine_threadsafe(
            progress_callback(self._seen_so_far, self._total_size, self._message, self._action, self._start_time),
            self._loop
        )

@app.on_message(filters.document | filters.video | filters.audio | filters.photo | filters.command("upload"))
async def upload_handler(client: Client, message: Message):
    """Handles file uploads."""
    if not s3_client:
        await message.reply_text("⚠️ **Connection Error:** Wasabi S3 client is not configured. Please check environment variables.")
        return

    file_message = message.reply_to_message if message.reply_to_message else message
    media = (
        file_message.document
        or file_message.video
        or file_message.audio
        or file_message.photo
    )

    if not media:
        await message.reply_text("Please reply to a file or send a file to upload.")
        return

    if media.file_size > 4 * 1024 * 1024 * 1024:
        await message.reply_text("❌ **Error:** File size exceeds the 4GB limit.")
        return

    # Download from Telegram
    status_msg = await message.reply_text("📥 Starting download from Telegram...", quote=True)
    start_time = time.time()
    file_path = await client.download_media(
        media,
        progress=progress_callback,
        progress_args=(status_msg, "Downloading", start_time),
    )
    
    await status_msg.edit_text("✅ Download complete. Now uploading to Wasabi...")

    # Upload to Wasabi
    file_id = media.file_unique_id
    file_name = getattr(media, "file_name", f"{file_id}.jpg") # Default for photos
    
    try:
        start_time_s3 = time.time()
        s3_client.upload_file(
            file_path,
            WASABI_BUCKET,
            file_name,
            Callback=S3Progress(status_msg, media.file_size, "Uploading", start_time_s3),
        )
        # Store file metadata
        file_db[file_id] = {
            "name": file_name,
            "size": media.file_size,
            "mime_type": media.mime_type,
            "tg_file_id": media.file_id,
        }
        
        # Backup to channel if set
        user_id = message.from_user.id
        if user_id in user_db and "channel_id" in user_db[user_id]:
            try:
                channel_id = user_db[user_id]["channel_id"]
                await client.send_document(channel_id, media.file_id, caption=f"**File:** `{file_name}`\n**ID:** `{file_id}`")
            except Exception as e:
                await message.reply_text(f"⚠️ Could not forward file to channel. Error: {e}")


        link = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": WASABI_BUCKET, "Key": file_name},
            ExpiresIn=3600 * 24 * 7,  # Link valid for 7 days
        )

        keyboard = get_file_actions_keyboard(file_id, link)
        await status_msg.edit_text(
            f"✅ **Upload Successful!**\n\n"
            f"**File Name:** `{file_name}`\n"
            f"**File Size:** `{human_readable_size(media.file_size)}`\n"
            f"**File ID:** `{file_id}`",
            reply_markup=keyboard
        )

    except ClientError as e:
        await status_msg.edit_text(f"❌ **Wasabi Upload Error:** {e}")
        LOGGER.error(f"Wasabi upload failed: {e}")
    except Exception as e:
        await status_msg.edit_text(f"❌ **An unexpected error occurred:** {e}")
        LOGGER.error(f"An unexpected error during upload: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.on_message(filters.command("list"))
async def list_files_command(_, message: Message):
    """Lists all stored files."""
    if not file_db:
        await message.reply_text("You haven't stored any files yet.")
        return

    response_text = "**🗂️ Stored Files:**\n\n"
    for file_id, data in file_db.items():
        response_text += f"- **{data['name']}** ({human_readable_size(data['size'])})\n  ID: `{file_id}`\n"

    await message.reply_text(response_text)


@app.on_message(filters.command(["download", "stream", "web"]))
async def get_file_command(_, message: Message):
    """Handles getting links for a file."""
    command = message.text.split()[0].lower()
    try:
        file_id = message.text.split()[1]
    except IndexError:
        await message.reply_text(f"Please provide a file ID. Usage: `{command} <file_id>`")
        return

    if file_id not in file_db:
        await message.reply_text("❌ **Error:** File ID not found.")
        return

    file_name = file_db[file_id]["name"]
    try:
        link = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": WASABI_BUCKET, "Key": file_name},
            ExpiresIn=3600 * 24,  # Link valid for 24 hours
        )
        
        keyboard = get_file_actions_keyboard(file_id, link)
        await message.reply_text(
            f"🔗 **Links for `{file_name}`**\n\n"
            f"Here are the links for your requested file. They are valid for 24 hours.",
            reply_markup=keyboard,
            quote=True
        )

    except ClientError as e:
        await message.reply_text(f"❌ **Could not generate link:** {e}")
        LOGGER.error(f"Failed to generate presigned URL for {file_id}: {e}")

@app.on_message(filters.command("setchannel"))
async def set_channel_command(_, message: Message):
    """Sets the backup channel."""
    try:
        channel_id = int(message.text.split()[1])
        user_id = message.from_user.id
        
        # A simple test to see if bot has permissions
        try:
            await app.get_chat(channel_id)
        except Exception as e:
            await message.reply_text(f"❌ **Error:** Could not access channel `{channel_id}`. Make sure the bot is an admin with posting rights. Error: {e}")
            return
            
        user_db[user_id] = {"channel_id": channel_id}
        await message.reply_text(f"✅ Backup channel has been set to `{channel_id}`.")
    except (IndexError, ValueError):
        await message.reply_text("Usage: `/setchannel <channel_id>`")


@app.on_message(filters.command("test"))
async def test_wasabi_connection(_, message: Message):
    """Tests the connection to Wasabi."""
    if not s3_client:
        await message.reply_text("❌ **Wasabi client is not initialized.** Check your environment variables and logs.")
        return
        
    try:
        s3_client.head_bucket(Bucket=WASABI_BUCKET)
        await message.reply_text(f"✅ **Success!** Connection to Wasabi bucket `{WASABI_BUCKET}` is working.")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            await message.reply_text(f"❌ **Error:** Bucket `{WASABI_BUCKET}` not found.")
        elif error_code == "403":
            await message.reply_text(f"❌ **Error:** Access denied to bucket `{WASABI_BUCKET}`. Check your keys and bucket permissions.")
        else:
            await message.reply_text(f"❌ **Connection Failed:** An S3 error occurred: {e}")
    except Exception as e:
        await message.reply_text(f"❌ **An unexpected error occurred:** {e}")

# --- Inline Keyboard and Callback Handling ---
def get_file_actions_keyboard(file_id, url):
    """Generates the inline keyboard for file actions."""
    # Note: A real web player would require a dedicated web service.
    # This is a placeholder link to a generic HTML5 video player.
    web_player_url = f"https://vjs.zencdn.net/v/oceans.mp4" # Placeholder, ideally use a service that can take a URL param
    
    keyboard = [
        [InlineKeyboardButton("📥 Direct Download", url=url)],
        [
            InlineKeyboardButton("▶️ MX Player", url=f"intent:{url}#Intent;package=com.mxtech.videoplayer.ad;end"),
            InlineKeyboardButton("▶️ VLC", url=f"vlc://{url}"),
        ],
        [InlineKeyboardButton("🌐 Web Player", url=web_player_url)],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Main Execution ---
if __name__ == "__main__":
    if not all([API_ID, API_HASH, BOT_TOKEN, WASABI_ACCESS_KEY, WASABI_SECRET_KEY, WASABI_BUCKET, WASABI_REGION]):
        LOGGER.error("One or more required environment variables are missing. Bot cannot start.")
    else:
        LOGGER.info("Bot is starting...")
        app.run()
