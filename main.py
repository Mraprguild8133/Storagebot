# Telegram Wasabi Bot
# This bot downloads files from Telegram, uploads them to Wasabi S3 storage,
# and provides an instant, shareable link.

import os
import time
import math
import asyncio
import aiohttp
from functools import wraps
from dotenv import load_dotenv

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Configuration Loading ---
# Load environment variables from a .env file for local development
load_dotenv()

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WASABI_ACCESS_KEY = os.environ.get("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.environ.get("WASABI_SECRET_KEY")
WASABI_BUCKET = os.environ.get("WASABI_BUCKET")
WASABI_REGION = os.environ.get("WASABI_REGION")
ADMIN_ID = os.environ.get("ADMIN_ID")
WELCOME_IMAGE_URL = os.environ.get("WELCOME_IMAGE_URL", "https://placehold.co/1280x720/1e293b/ffffff?text=Welcome!")

# --- Sanity Checks for Configuration ---
if not all([API_ID, API_HASH, BOT_TOKEN, WASABI_ACCESS_KEY, WASABI_SECRET_KEY, WASABI_BUCKET, WASABI_REGION, ADMIN_ID]):
    raise ValueError("One or more required environment variables are missing. Please check your configuration.")

try:
    API_ID = int(API_ID)
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise ValueError("API_ID and ADMIN_ID must be integers.")

# --- In-memory User Management ---
# For a production bot, consider a persistent database (e.g., SQLite, Redis).
AUTHORIZED_USERS = {ADMIN_ID}

# --- Boto3 S3 Client Initialization for Wasabi ---
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=f'https://s3.{WASABI_REGION}.wasabisys.com',
        aws_access_key_id=WASABI_ACCESS_KEY,
        aws_secret_access_key=WASABI_SECRET_KEY,
        region_name=WASABI_REGION
    )
except Exception as e:
    print(f"Error initializing Boto3 client: {e}")
    # Exit if we can't connect to Wasabi
    exit(1)


# --- Pyrogram Client Initialization ---
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
# We will attach the running event loop later in main()
app.loop = None

# --- Helper Functions ---
def humanbytes(size):
    """Converts bytes to a human-readable format."""
    if not size:
        return "0B"
    size = float(size)
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

def time_formatter(seconds: float) -> str:
    """Formats seconds into a human-readable string."""
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# --- Authorization Decorators ---
def admin_only(func):
    """Decorator to restrict a command to the admin."""
    @wraps(func)
    async def wrapped(client, message, *args, **kwargs):
        if message.from_user.id != ADMIN_ID:
            await message.reply_text("⛔️ **Access Denied:** You are not authorized to use this command.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapped

def authorized_user(func):
    """Decorator to restrict bot usage to authorized users."""
    @wraps(func)
    async def wrapped(client, message, *args, **kwargs):
        if message.from_user.id not in AUTHORIZED_USERS:
            await message.reply_text("⛔️ **Access Denied:** You are not authorized to use this bot. Please contact the admin.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapped

# --- Progress Callback Classes ---
class Boto3Progress:
    """
    Callback handler for Boto3 uploads to update the Telegram message.
    Handles the complexity of calling an async function from a sync callback.
    """
    def __init__(self, message, file_size, loop):
        self._message = message
        self._size = float(file_size)
        self._seen_so_far = 0
        self._loop = loop
        self._start_time = time.time()
        self._last_update_time = 0

    def __call__(self, bytes_amount):
        now = time.time()
        # Update Telegram message throttled to once every 2 seconds
        if now - self._last_update_time > 2.0 or self._seen_so_far == self._size:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            elapsed_time = now - self._start_time
            speed = self._seen_so_far / elapsed_time if elapsed_time > 0 else 0
            
            progress_str = f"[{'█' * int(percentage / 5)}{' ' * (20 - int(percentage / 5))}]"

            text = (
                f"**🚀 Uploading to Wasabi...**\n\n"
                f"`{progress_str}` **{percentage:.2f}%**\n\n"
                f"✅ **Uploaded:** {humanbytes(self._seen_so_far)} / {humanbytes(self._size)}\n"
                f"⚡️ **Speed:** {humanbytes(speed)}/s\n"
                f"⏳ **Elapsed:** {time_formatter(elapsed_time)}"
            )
            # Schedule the async message edit on the main event loop
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._message.edit_text(text), self._loop)
            self._last_update_time = now

# --- Telegram Command Handlers ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    """Handles the /start command."""
    if message.from_user.id not in AUTHORIZED_USERS:
         await message.reply_photo(
            photo=WELCOME_IMAGE_URL,
            caption="""
**Welcome to the File Upload Bot!** 🤖

This bot is private. To use this bot, you need authorization from the admin.
"""
        )
         return
    
    await message.reply_photo(
        photo=WELCOME_IMAGE_URL,
        caption=f"""
**Hi {message.from_user.first_name}, welcome!** 👋

I can upload files from Telegram directly to secure Wasabi cloud storage and provide you with an instant sharing link.

Just send me any file to get started!

Use /help to see all available commands.
"""
    )

@app.on_message(filters.command("help") & filters.private)
@authorized_user
async def help_command(client, message: Message):
    """Handles the /help command."""
    help_text = """
**Available Commands:**

`/start` - Shows the welcome message.
`/help` - Displays this help message.
`/speedtest` - Performs a real-time network speed test.

**Admin Commands:**
`/adduser <user_id>` - Authorizes a new user.
`/removeuser <user_id>` - Revokes a user's access.
`/listusers` - Lists all authorized user IDs.

**How to use:**
Simply send any file (document, video, audio) to this chat. I will handle the rest!
"""
    await message.reply_text(help_text)

@app.on_message(filters.command("adduser") & filters.private)
@admin_only
async def add_user_command(client, message: Message):
    """Admin command to add an authorized user."""
    try:
        user_id_to_add = int(message.command[1])
        AUTHORIZED_USERS.add(user_id_to_add)
        await message.reply_text(f"✅ **Success!** User `{user_id_to_add}` has been authorized.")
    except (ValueError, IndexError):
        await message.reply_text("⚠️ **Invalid format.** Please use: `/adduser <user_id>`")

@app.on_message(filters.command("removeuser") & filters.private)
@admin_only
async def remove_user_command(client, message: Message):
    """Admin command to remove an authorized user."""
    try:
        user_id_to_remove = int(message.command[1])
        if user_id_to_remove == ADMIN_ID:
            await message.reply_text("❌ **Error:** You cannot remove the admin.")
            return
        AUTHORIZED_USERS.discard(user_id_to_remove)
        await message.reply_text(f"✅ **Success!** User `{user_id_to_remove}` has been removed.")
    except (ValueError, IndexError):
        await message.reply_text("⚠️ **Invalid format.** Please use: `/removeuser <user_id>`")

@app.on_message(filters.command("listusers") & filters.private)
@admin_only
async def list_users_command(client, message: Message):
    """Admin command to list all authorized users."""
    if not AUTHORIZED_USERS:
        await message.reply_text("No users are authorized yet.")
        return
    
    user_list = "\n".join([f"- `{user_id}` {'(Admin)' if user_id == ADMIN_ID else ''}" for user_id in AUTHORIZED_USERS])
    await message.reply_text(f"**Authorized Users:**\n{user_list}")

@app.on_message(filters.command("speedtest") & filters.private)
@authorized_user
async def speed_test_command(client, message: Message):
    """Performs a network speed test."""
    status_msg = await message.reply_text("💨 **Running speed test...**\n\nPerforming download test...")
    test_file_url = "http://speed.hetzner.de/10MB.bin"
    file_path = "speedtest_10mb.bin"
    
    # Download Test
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(test_file_url) as response:
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during download test:** {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return
        
    end_time = time.time()
    download_duration = end_time - start_time
    file_size_bytes = os.path.getsize(file_path)
    download_speed = file_size_bytes / download_duration
    
    await status_msg.edit_text(
        f"💨 **Running speed test...**\n\n"
        f"✅ **Download:** {humanbytes(download_speed)}/s\n"
        f"📤 Performing upload test..."
    )

    # Upload Test
    start_time = time.time()
    try:
        s3_client.upload_file(file_path, WASABI_BUCKET, os.path.basename(file_path))
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during upload test:** {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return
    end_time = time.time()
    upload_duration = end_time - start_time
    upload_speed = file_size_bytes / upload_duration

    await status_msg.edit_text(
        f"**🏁 Speed Test Complete!**\n\n"
        f"🔽 **Download Speed:** {humanbytes(download_speed)}/s\n"
        f"🔼 **Upload Speed:** {humanbytes(upload_speed)}/s"
    )

    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)
    try:
        s3_client.delete_object(Bucket=WASABI_BUCKET, Key=os.path.basename(file_path))
    except Exception:
        pass # Ignore cleanup error


# --- Main File Handling Logic ---
@app.on_message((filters.document | filters.video | filters.audio) & filters.private)
@authorized_user
async def file_handler(client: Client, message: Message):
    """Handles incoming files, downloads them, and uploads to Wasabi."""
    media = message.document or message.video or message.audio
    if not media:
        await message.reply_text("Unsupported file type.")
        return
    
    file_name = media.file_name
    file_size = media.file_size
    
    if file_size > 4 * 1024 * 1024 * 1024:
        await message.reply_text("❌ **Error:** File is larger than the 4GB limit.")
        return

    download_path = f"./downloads/{file_name}"
    os.makedirs(os.path.dirname(download_path), exist_ok=True)

    status_msg = await message.reply_text(f"📥 **Starting download:** `{file_name}`")
    
    start_time = time.time()
    last_update_time_tg = [0] # Use a list to make it mutable in the closure

    async def download_progress_callback(current, total):
        now = time.time()
        if now - last_update_time_tg[0] > 2.0:
            percentage = (current / total) * 100
            elapsed_time = now - start_time
            speed = current / elapsed_time if elapsed_time > 0 else 0
            progress_str = f"[{'█' * int(percentage / 5)}{' ' * (20 - int(percentage / 5))}]"
            
            text = (
                f"**📥 Downloading from Telegram...**\n\n"
                f"`{progress_str}` **{percentage:.2f}%**\n\n"
                f"✅ **Downloaded:** {humanbytes(current)} / {humanbytes(total)}\n"
                f"⚡️ **Speed:** {humanbytes(speed)}/s\n"
                f"⏳ **Elapsed:** {time_formatter(elapsed_time)}"
            )
            try:
                await status_msg.edit_text(text)
                last_update_time_tg[0] = now
            except:
                pass # Ignore errors if message not modified

    try:
        await client.download_media(
            message=message,
            file_name=download_path,
            progress=download_progress_callback
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during download:** {e}")
        if os.path.exists(download_path):
            os.remove(download_path)
        return

    await status_msg.edit_text("✅ **Download complete!**\n\nStarting upload to Wasabi...")

    # Upload to Wasabi
    try:
        boto_progress = Boto3Progress(status_msg, file_size, app.loop)
        # Boto3 is synchronous, run it in a thread to avoid blocking the event loop
        await asyncio.to_thread(
            s3_client.upload_file,
            download_path,
            WASABI_BUCKET,
            file_name,
            Callback=boto_progress
        )
    except NoCredentialsError:
        await status_msg.edit_text("❌ **Configuration Error:** Wasabi credentials not found.")
        return
    except ClientError as e:
        await status_msg.edit_text(f"❌ **Wasabi Error:** {e.response['Error']['Message']}")
        return
    except Exception as e:
        await status_msg.edit_text(f"❌ **An unexpected error occurred during upload:** {e}")
        return
    finally:
        if os.path.exists(download_path):
            os.remove(download_path) # Clean up downloaded file

    # Generate presigned URL
    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': WASABI_BUCKET, 'Key': file_name},
            ExpiresIn=3600 * 24 * 7  # Link valid for 7 days
        )
        
        final_caption = (
            f"**✅ Upload Successful!**\n\n"
            f"**File:** `{file_name}`\n"
            f"**Size:** {humanbytes(file_size)}\n\n"
            f"🔗 **Your link is ready:**\n"
        )

        await status_msg.edit_text(final_caption)
        await message.reply_text(f"`{presigned_url}`", quote=True)

    except Exception as e:
        await status_msg.edit_text(f"❌ **Could not generate link:** {e}")

# --- Main Bot Execution ---
async def main():
    """Starts the bot and keeps it running."""
    global app
    await app.start()
    print("Bot has started successfully!")
    # Attach the running event loop to the app instance for the Boto3 callback
    app.loop = asyncio.get_running_loop()
    
    try:
        # Keep the bot running indefinitely
        await asyncio.Future()
    except KeyboardInterrupt:
        print("Bot is shutting down...")
    finally:
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"An error occurred during bot execution: {e}")
