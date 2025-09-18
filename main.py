import os
import time
import asyncio
import logging
import random
from threading import Lock

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, SessionPasswordNeeded, BadRequest

import boto3
from botocore.exceptions import ClientError
from botocore.client import Config

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce logging noise
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

# --- Generate unique session name ---
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
            if current_time - self.last_update_time < 2:
                return
                
            self.last_update_time = current_time
            
            # Calculate progress metrics
            elapsed_time = current_time - self.start_time
            speed = self.uploaded / elapsed_time if elapsed_time > 0 else 0
            percentage = min(100, (self.uploaded / self.total_size) * 100)
            
            # Create progress bar
            progress_bar = '█' * int(percentage / 5) + ' ' * (20 - int(percentage / 5))
            
            # Calculate ETA safely
            remaining_bytes = max(0, self.total_size - self.uploaded)
            eta_seconds = remaining_bytes / speed if speed > 0 else 0
            eta_str = self.get_readable_time(eta_seconds) if speed > 0 else '...'
            
            progress_str = (
                f"**Uploading to Wasabi...**\n"
                f"[{progress_bar}] {percentage:.1f}%\n"
                f"**Done:** {self.get_readable_file_size(self.uploaded)}\n"
                f"**Total:** {self.get_readable_file_size(self.total_size)}\n"
                f"**Speed:** {self.get_readable_file_size(speed)}/s\n"
                f"**ETA:** {eta_str}"
            )
            
            # Schedule the message update
            try:
                asyncio.run_coroutine_threadsafe(
                    self.safe_update_message(progress_str),
                    self.loop
                )
            except Exception as e:
                logger.warning(f"Failed to schedule progress update: {e}")
    
    async def safe_update_message(self, progress_str):
        try:
            await self.status_msg.edit_text(progress_str)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except BadRequest as e:
            if "message not found" in str(e).lower():
                self.is_cancelled = True
        except Exception as e:
            logger.warning(f"Error updating progress: {e}")
    
    def get_readable_file_size(self, size_in_bytes):
        if size_in_bytes <= 0:
            return "0B"
        power = 1024
        n = 0
        power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size_in_bytes >= power and n < len(power_labels) - 1:
            size_in_bytes /= power
            n += 1
        return f"{size_in_bytes:.2f} {power_labels[n]}B"
    
    def get_readable_time(self, seconds):
        if seconds <= 0:
            return "0s"
        seconds = round(seconds)
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
        if seconds > 0 or not result:
            result += f"{seconds}s"
        return result.strip()

# --- Decorators ---
def admin_only(func):
    async def wrapped(client, message):
        if message.from_user.id != ADMIN_ID:
            await message.reply_text("You are not authorized to use this command.")
            return
        await func(client, message)
    return wrapped

def authorized_only(func):
    async def wrapped(client, message):
        if message.from_user.id not in AUTHORIZED_USERS:
            await message.reply_text("You are not a premium user. Please contact the admin.")
            return
        await func(client, message)
    return wrapped

# --- Helper Functions ---
def get_readable_file_size(size_in_bytes):
    if size_in_bytes <= 0:
        return "0B"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size_in_bytes >= power and n < len(power_labels) - 1:
        size_in_bytes /= power
        n += 1
    return f"{size_in_bytes:.2f} {power_labels[n]}B"

def get_readable_time(seconds):
    if seconds <= 0:
        return "0s"
    seconds = round(seconds)
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
    if seconds > 0 or not result:
        result += f"{seconds}s"
    return result.strip()

# --- Download Function ---
async def download_file_with_progress(client, message, file_name, file_size, status_msg):
    file_path = f"./downloads/{file_name}"
    os.makedirs("./downloads", exist_ok=True)
    
    start_time = time.time()
    last_update_time = start_time
    
    async def update_progress(current, total):
        nonlocal last_update_time
        current_time = time.time()
        
        if current_time - last_update_time < 2:
            return
            
        last_update_time = current_time
        elapsed_time = current_time - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        percentage = min(100, (current / total) * 100)
        
        progress_bar = '█' * int(percentage / 5) + ' ' * (20 - int(percentage / 5))
        
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
        file_path = await client.download_media(
            message,
            file_name=file_path,
            progress=update_progress
        )
        
        if file_path and os.path.exists(file_path):
            downloaded_size = os.path.getsize(file_path)
            if abs(downloaded_size - file_size) > 1024:
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
    max_retries = 3
    retry_delay = 5
    
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
            
            # Force final update
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
            logger.error(f"Wasabi upload error (attempt {attempt + 1}/{max_retries}): {error_code}")
            
            if attempt < max_retries - 1:
                await status_msg.edit_text(f"Upload failed ({error_code}). Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
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
async def start_command(client, message):
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
            "- Upload files up to 4GB\n"
            "- Real-time progress monitoring\n"
            "- Direct download links\n\n"
            "Send me any file to get started!"
        )
    )

@app.on_message(filters.command("adduser") & filters.private)
@admin_only
async def add_user_command(client, message):
    try:
        user_id_to_add = int(message.text.split()[1])
        AUTHORIZED_USERS.add(user_id_to_add)
        await message.reply_text(f"User {user_id_to_add} added successfully.")
    except (IndexError, ValueError):
        await message.reply_text("Usage: /adduser USER_ID")

@app.on_message(filters.command("removeuser") & filters.private)
@admin_only
async def remove_user_command(client, message):
    try:
        user_id_to_remove = int(message.text.split()[1])
        if user_id_to_remove == ADMIN_ID:
            await message.reply_text("Cannot remove admin.")
            return
        if user_id_to_remove in AUTHORIZED_USERS:
            AUTHORIZED_USERS.remove(user_id_to_remove)
            await message.reply_text(f"User {user_id_to_remove} removed.")
        else:
            await message.reply_text("User not found.")
    except (IndexError, ValueError):
        await message.reply_text("Usage: /removeuser USER_ID")

@app.on_message(filters.command("listusers") & filters.private)
@admin_only
async def list_users_command(client, message):
    if not AUTHORIZED_USERS:
        await message.reply_text("No authorized users.")
        return
    
    user_list = "\n".join([f"- {user_id}" for user_id in AUTHORIZED_USERS])
    await message.reply_text(f"Authorized Users:\n{user_list}")

# --- File Handler ---
@app.on_message(
    (filters.document | filters.video | filters.audio | filters.photo) &
    filters.private
)
@authorized_only
async def file_handler(client, message):
    if not s3_client:
        await message.reply_text("Wasabi client not configured.")
        return

    media = message.document or message.video or message.audio or message.photo
    if media.file_size > 4 * 1024 * 1024 * 1024:
        await message.reply_text("File too large (max 4GB).")
        return

    file_name = media.file_name if hasattr(media, 'file_name') and media.file_name else f"file_{media.file_unique_id}"
    file_size = media.file_size
    
    status_msg = await message.reply_text("Starting download...")

    try:
        file_path = await download_file_with_progress(
            client, message, file_name, file_size, status_msg
        )
        
        if not file_path:
            await status_msg.edit_text("Download failed.")
            return
            
        await status_msg.edit_text("Download complete. Uploading to Wasabi...")
        
        progress_tracker = UploadProgress(status_msg, file_size, asyncio.get_event_loop())
        success = await upload_to_wasabi(file_path, file_name, status_msg, progress_tracker)
        
        if not success:
            await status_msg.edit_text("Upload failed after retries.")
            return
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': WASABI_BUCKET, 'Key': file_name},
            ExpiresIn=604800  # 7 days
        )
        
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Download / Stream", url=presigned_url)]]
        )

        await status_msg.edit_text(
            f"**Upload Successful!**\n\n"
            f"**File:** `{file_name}`\n"
            f"**Size:** {get_readable_file_size(file_size)}\n"
            f"**Link valid for 7 days**",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        try:
            await status_msg.edit_text(f"Error: {str(e)}")
        except:
            await message.reply_text(f"Error: {str(e)}")
    finally:
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

# --- Main Function ---
async def main():
    # Check environment variables
    required_vars = ["API_ID", "API_HASH", "BOT_TOKEN", "WASABI_ACCESS_KEY", 
                    "WASABI_SECRET_KEY", "WASABI_BUCKET", "WASABI_REGION", "ADMIN_ID"]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        logger.critical(f"Missing environment variables: {missing_vars}")
        return

    # Create directories
    os.makedirs("./downloads", exist_ok=True)
    
    # Clean up old session files
    for file in os.listdir('.'):
        if file.startswith('wasabi_bot') and file.endswith('.session'):
            try:
                os.remove(file)
                logger.info(f"Removed old session: {file}")
            except:
                pass
    
    # Start the bot
    try:
        await app.start()
        me = await app.get_me()
        logger.info(f"Bot started as @{me.username}")
        
        # Keep running
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    finally:
        if await app.is_connected:
            await app.stop()
            logger.info("Bot stopped")

if __name__ == "__main__":
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
