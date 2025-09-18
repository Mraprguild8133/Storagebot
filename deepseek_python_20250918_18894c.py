import os
import time
import asyncio
import logging
import random
import functools
from datetime import datetime
from threading import Lock
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, SessionPasswordNeeded, BadRequest

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from botocore.client import Config

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce logging noise from asyncio and aiohttp
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

# --- Environment Variables ---
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WASABI_ACCESS_KEY = os.environ.get("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.environ.get("WASABI_SECRET_KEY")
WASABI_BUCKET = os.environ.get("WASABI_BUCKET")
WASABI_REGION = os.environ.get("WASABI_REGION")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
WELCOME_IMAGE_URL = os.environ.get("WELCOME_IMAGE_URL", "https://placehold.co/1280x720/4B5563/FFFFFF?text=Welcome!")

# --- In-memory "Database" for authorized users ---
AUTHORIZED_USERS = {ADMIN_ID} if ADMIN_ID else set()

# --- Wasabi S3 Client ---
s3_client = None
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=f'https://s3.{WASABI_REGION}.wasabisys.com',
        aws_access_key_id=WASABI_ACCESS_KEY,
        aws_secret_access_key=WASABI_SECRET_KEY,
        config=Config(
            signature_version='s3v4',
            retries={'max_attempts': 3, 'mode': 'standard'},
            connect_timeout=30,
            read_timeout=60
        ),
        region_name=WASABI_REGION
    )
    logger.info("Wasabi client initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Wasabi client: {e}")

# --- Generate unique session name to avoid conflicts ---
SESSION_NAME = f"wasabi_bot_{random.randint(1000, 9999)}"

# --- Pyrogram Client ---
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Thread-safe progress tracking ---
class UploadProgress:
    def __init__(self, status_msg, total_size, loop):
        self.status_msg = status_msg
        self.total_size = total_size
        self.uploaded = 0
        self.start_time = time.time()
        self.lock = Lock()
        self.last_update_time = 0
        self.loop = loop
        self.is_cancelled = False
        self.is_completed = False
        
    def update(self, bytes_amount):
        if self.is_cancelled or self.is_completed:
            return
            
        with self.lock:
            self.uploaded += bytes_amount
            
            # Check if upload is complete (within 1KB tolerance)
            if abs(self.uploaded - self.total_size) < 1024:
                self.is_completed = True
                return
                
            current_time = time.time()
            
            # Throttle updates to avoid FloodWait errors
            if current_time - self.last_update_time < 2:  # Update at most once every 2 seconds
                return
                
            self.last_update_time = current_time
            
            # Calculate progress metrics
            elapsed_time = current_time - self.start_time
            speed = self.uploaded / elapsed_time if elapsed_time > 0 else 0
            percentage = min(100, (self.uploaded / self.total_size) * 100) if self.total_size > 0 else 0
            
            # Create progress bar
            progress_bar = '█' * int(percentage / 5) + ' ' * (20 - int(percentage / 5))
            
            # Calculate ETA safely
            remaining_bytes = max(0, self.total_size - self.uploaded)
            eta_seconds = remaining_bytes / speed if speed > 0 else 0
            eta_str = get_readable_time(eta_seconds) if speed > 0 else '...'
            
            progress_str = (
                f"**Uploading to Wasabi...**\n"
                f"[{progress_bar}] {percentage:.1f}%\n"
                f"**Done:** {get_readable_file_size(self.uploaded)}\n"
                f"**Total:** {get_readable_file_size(self.total_size)}\n"
                f"**Speed:** {get_readable_file_size(speed)}/s\n"
                f"**ETA:** {eta_str}"
            )
            
            # Schedule the message update in the asyncio event loop
            try:
                asyncio.run_coroutine_threadsafe(
                    self.safe_update_message(progress_str),
                    self.loop
                )
            except Exception as e:
                logger.warning(f"Failed to schedule progress update: {e}")
    
    async def safe_update_message(self, progress_str):
        """Safely update the message with error handling"""
        try:
            await self.status_msg.edit_text(progress_str)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except BadRequest as e:
            if "message not found" in str(e).lower():
                self.is_cancelled = True
                logger.warning("Message was deleted, cancelling upload progress updates")
        except Exception as e:
            logger.warning(f"Error updating progress: {e}")
    
    def cancel(self):
        self.is_cancelled = True

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
    if size_in_bytes is None or size_in_bytes <= 0:
        return "0B"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size_in_bytes >= power and n < len(power_labels) - 1:
        size_in_bytes /= power
        n += 1
    return f"{size_in_bytes:.2f} {power_labels[n]}B"

def get_readable_time(seconds: float) -> str:
    """Converts seconds to a human-readable format."""
    if seconds <= 0:
        return "0s"
    
    # Round to nearest whole number to avoid decimal issues
    seconds = round(seconds)
    
    result = ""
    if seconds >= 86400:
        days = int(seconds // 86400)
        result += f"{days}d "
        seconds %= 86400
    if seconds >= 3600:
        hours = int(seconds // 3600)
        result += f"{hours}h "
        seconds %= 3600
    if seconds >= 60:
        minutes = int(seconds // 60)
        result += f"{minutes}m "
        seconds %= 60
    
    # Only show seconds if less than a minute, or as part of larger time
    if seconds > 0 or not result:
        result += f"{int(seconds)}s"
    
    return result.strip()

# --- Fast Download Function ---
async def download_file_with_progress(client, message, file_name, file_size, status_msg):
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
        if current_time - last_update_time < 2:  # Update at most once every 2 seconds
            return
            
        last_update_time = current_time
        elapsed_time = current_time - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        percentage = min(100, (current / total) * 100) if total > 0 else 0
        
        progress_bar = '█' * int(percentage / 5) + ' ' * (20 - int(percentage / 5))
        
        # Calculate ETA safely
        remaining_bytes = max(0, total - current)
        eta_seconds = remaining_bytes / speed if speed > 0 else 0
        eta_str = get_readable_time(eta_seconds) if speed > 0 else '...'
        
        progress_str = (
            f"**Downloading from Telegram...**\n"
            f"[{progress_bar}] {percentage:.1f}%\n"
            f"**Done:** {get_readable_file_size(current)}\n"
            f"**Total:** {get_readable_file_size(total)}\n"
            f"**Speed:** {get_readable_file_size(speed)}/s\n"
            f"**ETA:** {eta_str}"
        )
        
        try:
            await status_msg.edit_text(progress_str)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except Exception as e:
            logger.warning(f"Error updating download progress: {e}")
    
    try:
        # Use pyrogram's download method which is optimized
        file_path = await client.download_media(
            message,
            file_name=file_path,
            progress=update_progress
        )
        
        # Verify file size
        if file_path and os.path.exists(file_path):
            downloaded_size = os.path.getsize(file_path)
            if abs(downloaded_size - file_size) > 1024:  # Allow 1KB tolerance
                logger.warning(f"File size mismatch: expected {file_size}, got {downloaded_size}")
        
        return file_path
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        raise e

async def upload_to_wasabi(file_path, file_name, status_msg, progress_tracker):
    """Upload file to Wasabi with proper error handling"""
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            with open(file_path, 'rb') as file_data:
                s3_client.upload_fileobj(
                    file_data,
                    WASABI_BUCKET,
                    file_name,
                    Callback=progress_tracker.update,
                    ExtraArgs={
                        'ACL': 'public-read',
                        'ContentType': 'application/octet-stream'
                    }
                )
            
            # Force final update to show 100% completion
            progress_tracker.uploaded = progress_tracker.total_size
            final_progress = (
                f"**Upload Complete!**\n"
                f"[{'█' * 20}] 100.0%\n"
                f"**Done:** {get_readable_file_size(progress_tracker.total_size)}\n"
                f"**Total:** {get_readable_file_size(progress_tracker.total_size)}\n"
                f"**Finalizing...**"
            )
            
            try:
                await status_msg.edit_text(final_progress)
            except:
                pass
                
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Wasabi upload error (attempt {attempt + 1}/{max_retries}): {error_code} - {e}")
            
            if attempt < max_retries - 1:
                await status_msg.edit_text(f"Upload failed ({error_code}). Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                raise e
                
        except Exception as e:
            logger.error(f"Unexpected upload error (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                await status_msg.edit_text(f"Upload failed. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise e
    
    return False

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
            client, message, file_name, file_size, status_msg
        )
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("Failed to download the file.")
            return
            
        await status_msg.edit_text("Download complete. Starting upload to Wasabi...")
        
        # Upload to Wasabi with progress
        progress_tracker = UploadProgress(status_msg, file_size, asyncio.get_event_loop())
        
        # Upload with retry mechanism
        success = await upload_to_wasabi(file_path, file_name, status_msg, progress_tracker)
        
        if not success:
            await status_msg.edit_text("Upload failed after retry. Please try again later.")
            return
        
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
        error_msg = f"Failed to process file: {str(e)}"
        if "Timeout" in str(e) or "socket" in str(e).lower():
            error_msg = "Network timeout during upload. Please try again with a smaller file or better connection."
        
        try:
            await status_msg.edit_text(error_msg)
        except:
            await message.reply_text(error_msg)
    finally:
        # Clean up downloaded file
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

async def main():
    if not all([API_ID, API_HASH, BOT_TOKEN, WASABI_ACCESS_KEY, WASABI_SECRET_KEY, WASABI_BUCKET, WASABI_REGION, ADMIN_ID]):
        logger.critical("One or more environment variables are missing. Bot cannot start.")
        return

    # Create downloads directory if it doesn't exist
    if not os.path.isdir("downloads"):
        os.makedirs("./downloads", exist_ok=True)
    
    # Clean up any existing session files to avoid conflicts
    session_files = [f for f in os.listdir('.') if f.startswith('wasabi_bot') and f.endswith('.session')]
    for file in session_files:
        try:
            os.remove(file)
            logger.info(f"Removed old session file: {file}")
        except:
            pass
    
    try:
        await app.start()
        logger.info("Bot started successfully!")
        
        # Get bot info to verify connection
        me = await app.get_me()
        logger.info(f"Bot is running as @{me.username}")
        
        # Keep the bot running
        await asyncio.Event().wait()
        
    except SessionPasswordNeeded:
        logger.error("Two-factor authentication is enabled. This bot cannot handle 2FA.")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    finally:
        if app.is_connected:
            await app.stop()
            logger.info("Bot stopped successfully.")

if __name__ == "__main__":
    # Set up proper event loop policy for Windows compatibility
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")