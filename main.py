import os
import time
import asyncio
import logging
from datetime import datetime
from threading import Lock
import aiohttp
import aiofiles

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

import boto3
from botocore.exceptions import NoCredentialsError
from botocore.client import Config

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Environment Variables ---
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WASABI_ACCESS_KEY = os.environ.get("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.environ.get("WASABI_SECRET_KEY")
WASABI_BUCKET = os.environ.get("WASABI_BUCKET")
WASABI_REGION = os.environ.get("WASABI_REGION")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))  # Add your Telegram User ID as the main admin
WELCOME_IMAGE_URL = os.environ.get("WELCOME_IMAGE_URL", "https://placehold.co/1280x720/4B5563/FFFFFF?text=Welcome!")

# --- In-memory "Database" for authorized users ---
AUTHORIZED_USERS = {ADMIN_ID} if ADMIN_ID else set()

# --- Wasabi S3 Client ---
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=f'https://s3.{WASABI_REGION}.wasabisys.com',
        aws_access_key_id=WASABI_ACCESS_KEY,
        aws_secret_access_key=WASABI_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name=WASABI_REGION
    )
    logger.info("Wasabi client initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Wasabi client: {e}")
    s3_client = None

# --- Pyrogram Client ---
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Thread-safe progress tracking ---
class UploadProgress:
    def __init__(self, status_msg, total_size):
        self.status_msg = status_msg
        self.total_size = total_size
        self.uploaded = 0
        self.start_time = time.time()
        self.lock = Lock()
        self.last_update_time = 0
        
    def update(self, bytes_amount):
        with self.lock:
            self.uploaded += bytes_amount
            current_time = time.time()
            
            # Throttle updates to avoid FloodWait errors
            if current_time - self.last_update_time < 1:  # Update at most once per second
                return
                
            self.last_update_time = current_time
            
            # Calculate progress metrics
            elapsed_time = current_time - self.start_time
            speed = self.uploaded / elapsed_time if elapsed_time > 0 else 0
            percentage = (self.uploaded / self.total_size) * 100
            
            progress_str = (
                f"**Uploading to Wasabi...**\n"
                f"[{'█' * int(percentage / 5)}{' ' * (20 - int(percentage / 5))}] {percentage:.1f}%\n"
                f"**Done:** {get_readable_file_size(self.uploaded)}\n"
                f"**Total:** {get_readable_file_size(self.total_size)}\n"
                f"**Speed:** {get_readable_file_size(speed)}/s\n"
                f"**ETA:** {get_readable_time((self.total_size - self.uploaded) / speed) if speed > 0 else '...'}"
            )
            
            # Schedule the message update in the asyncio event loop
            asyncio.run_coroutine_threadsafe(
                self.update_message(progress_str),
                asyncio.get_event_loop()
            )
    
    async def update_message(self, progress_str):
        try:
            await self.status_msg.edit_text(progress_str)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except Exception as e:
            logger.error(f"Error updating progress: {e}")

# --- Decorators ---
def admin_only(func):
    """Decorator to restrict access to the admin only."""
    async def wrapped(client, message):
        if message.from_user.id != ADMIN_ID:
            await message.reply_text("You are not authorized to use this command.")
            return
        await func(client, message)
    return wrapped

def authorized_only(func):
    """Decorator to restrict access to authorized users only."""
    async def wrapped(client, message):
        if message.from_user.id not in AUTHORIZED_USERS:
            await message.reply_text("You are not a premium user. Please contact the admin.")
            return
        await func(client, message)
    return wrapped

# --- Helper Functions ---
def get_readable_file_size(size_in_bytes: int) -> str:
    """Converts a size in bytes to a human-readable format."""
    if size_in_bytes is None:
        return "0B"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size_in_bytes > power:
        size_in_bytes /= power
        n += 1
    return f"{size_in_bytes:.2f} {power_labels[n]}B"

def get_readable_time(seconds: int) -> str:
    """Converts seconds to a human-readable format."""
    result = ""
    if seconds >= 86400:
        days = seconds // 86400
        result += f"{days}d "
        seconds %= 86400
    if seconds >= 3600:
        hours = seconds // 3600
        result += f"{hours}h "
        seconds %= 3600
    if seconds >= 60:
        minutes = seconds // 60
        result += f"{minutes}m "
        seconds %= 60
    result += f"{seconds}s"
    return result

# --- Fast Download Function ---
async def download_file_with_progress(client, message, file_id, file_name, file_size, status_msg):
    """Download file with progress using aiohttp for faster downloads"""
    file_path = f"./downloads/{file_name}"
    
    # Create downloads directory if it doesn't exist
    os.makedirs("./downloads", exist_ok=True)
    
    start_time = time.time()
    last_update_time = start_time
    
    # Create a progress callback that accepts the required parameters
    async def update_progress(current, total):
        nonlocal last_update_time
        current_time = time.time()
        
        # Throttle updates to avoid FloodWait errors
        if current_time - last_update_time < 1:  # Update at most once per second
            return
            
        last_update_time = current_time
        elapsed_time = current_time - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        percentage = (current / total) * 100
        
        progress_str = (
            f"**Downloading from Telegram...**\n"
            f"[{'█' * int(percentage / 5)}{' ' * (20 - int(percentage / 5))}] {percentage:.1f}%\n"
            f"**Done:** {get_readable_file_size(current)}\n"
            f"**Total:** {get_readable_file_size(total)}\n"
            f"**Speed:** {get_readable_file_size(speed)}/s\n"
            f"**ETA:** {get_readable_time((total - current) / speed) if speed > 0 else '...'}"
        )
        
        try:
            await status_msg.edit_text(progress_str)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except Exception as e:
            logger.error(f"Error updating progress: {e}")
    
    try:
        # Use pyrogram's download method which is optimized
        download_task = app.download_media(
            message,
            file_name=file_path,
            progress=update_progress
        )
        
        # Wait for download to complete
        await download_task
        
        # Verify file size
        downloaded_size = os.path.getsize(file_path)
        if downloaded_size != file_size:
            logger.warning(f"File size mismatch: expected {file_size}, got {downloaded_size}")
        
        return file_path
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e

# --- Bot Commands ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply_photo(
            photo=WELCOME_IMAGE_URL,
            caption="Hello! You are not authorized to use this bot. Please contact the admin for access."
        )
        return

    await message.reply_photo(
        photo=WELCOME_IMAGE_URL,
        caption=(
            f"Hello {message.from_user.first_name}!\n\n"
            "I can upload files to Wasabi storage and generate shareable links.\n\n"
            "**Features:**\n"
            "- Upload files up to 4GB.\n"
            "- Real-time progress and speed monitoring.\n"
            "- Generate direct download/streaming links.\n\n"
            "Simply send me any file to get started!"
        )
    )

@app.on_message(filters.command("adduser") & filters.private)
@admin_only
async def add_user_command(client: Client, message: Message):
    try:
        user_id_to_add = int(message.text.split(" ", 1)[1])
        AUTHORIZED_USERS.add(user_id_to_add)
        await message.reply_text(f"User `{user_id_to_add}` has been added successfully.")
    except (IndexError, ValueError):
        await message.reply_text("Please provide a valid User ID. Usage: `/adduser 123456789`")

@app.on_message(filters.command("removeuser") & filters.private)
@admin_only
async def remove_user_command(client: Client, message: Message):
    try:
        user_id_to_remove = int(message.text.split(" ", 1)[1])
        if user_id_to_remove == ADMIN_ID:
            await message.reply_text("You cannot remove the admin.")
            return
        if user_id_to_remove in AUTHORIZED_USERS:
            AUTHORIZED_USERS.remove(user_id_to_remove)
            await message.reply_text(f"User `{user_id_to_remove}` has been removed.")
        else:
            await message.reply_text("User not found in the authorized list.")
    except (IndexError, ValueError):
        await message.reply_text("Please provide a valid User ID. Usage: `/removeuser 123456789`")

@app.on_message(filters.command("listusers") & filters.private)
@admin_only
async def list_users_command(client: Client, message: Message):
    if not AUTHORIZED_USERS:
        await message.reply_text("No users are authorized yet.")
        return
    
    user_list = "\n".join([f"- `{user_id}`" for user_id in AUTHORIZED_USERS])
    await message.reply_text(f"**Authorized Users:**\n{user_list}")

# --- File Handling ---
@app.on_message(
    (filters.document | filters.video | filters.audio | filters.photo) &
    filters.private
)
@authorized_only
async def file_handler(client: Client, message: Message):
    if not s3_client:
        await message.reply_text("Wasabi client is not configured. Please check the logs.")
        return

    media = message.document or message.video or message.audio or message.photo
    if media.file_size > 4 * 1024 * 1024 * 1024:
        await message.reply_text("File size is larger than 4GB. This is not supported.")
        return

    file_name = media.file_name if hasattr(media, 'file_name') and media.file_name else f"file_{media.file_unique_id}"
    file_size = media.file_size
    
    start_time = time.time()
    status_msg = await message.reply_text("Starting download from Telegram...")

    try:
        # Download file with progress
        file_path = await download_file_with_progress(
            client, message, media.file_id, file_name, file_size, status_msg
        )
        
        await status_msg.edit_text("Download complete. Starting upload to Wasabi...")
        
        # Upload to Wasabi with progress
        upload_progress = UploadProgress(status_msg, file_size)
        
        s3_client.upload_file(
            file_path,
            WASABI_BUCKET,
            file_name,
            Callback=upload_progress.update
        )
        
        # Generate Presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': WASABI_BUCKET, 'Key': file_name},
            ExpiresIn=3600 * 24 * 7  # 7 days
        )
        
        # Final Message
        end_time = time.time()
        total_time_taken = get_readable_time(int(end_time - start_time))
        
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Download / Stream Now", url=presigned_url)]]
        )

        await status_msg.edit_text(
            (
                f"**Upload Successful!**\n\n"
                f"**File Name:** `{file_name}`\n"
                f"**File Size:** {get_readable_file_size(file_size)}\n"
                f"**Time Taken:** {total_time_taken}\n\n"
                "The link will be valid for 7 days."
            ),
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        await status_msg.edit_text(f"Failed to process file: {e}")
    finally:
        # Clean up downloaded file
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

async def main():
    if not all([API_ID, API_HASH, BOT_TOKEN, WASABI_ACCESS_KEY, WASABI_SECRET_KEY, WASABI_BUCKET, WASABI_REGION, ADMIN_ID]):
        logger.critical("One or more environment variables are missing. Bot cannot start.")
        return

    # Create downloads directory if it doesn't exist
    if not os.path.isdir("downloads"):
        os.makedirs("downloads")
        
    await app.start()
    logger.info("Bot started successfully!")
    await asyncio.Event().wait()  # Keep the bot running

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    finally:
        if app.is_connected:
            loop.run_until_complete(app.stop())
