# Telegram Wasabi Bot
# This bot downloads files from Telegram, uploads them to Wasabi S3 storage,
# and provides an instant, shareable link.

import os
import time
import math
import asyncio
import aiohttp
import aiofiles
from functools import wraps
from dotenv import load_dotenv

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Configuration Loading ---
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
    
    # Test the connection
    s3_client.head_bucket(Bucket=WASABI_BUCKET)
    print("✅ Successfully connected to Wasabi S3 bucket")
except Exception as e:
    print(f"❌ Error initializing Boto3 client: {e}")
    exit(1)

# Create downloads directory if it doesn't exist
os.makedirs("./downloads", exist_ok=True)

# --- Pyrogram Client Initialization ---
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
    test_file_url = "http://ipv4.download.thinkbroadband.com/10MB.zip"  # More reliable test file
    file_path = "speedtest_10mb.zip"
    
    # Download Test
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(test_file_url) as response:
                response.raise_for_status()
                async with aiofiles.open(file_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        await f.write(chunk)
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
        # Use a different key for the upload test to avoid conflicts
        test_key = f"speedtest_{int(time.time())}.zip"
        s3_client.upload_file(file_path, WASABI_BUCKET, test_key)
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
        s3_client.delete_object(Bucket=WASABI_BUCKET, Key=test_key)
    except Exception:
        pass  # Ignore cleanup error

# --- Main File Handling Logic ---
@app.on_message((filters.document | filters.video | filters.audio) & filters.private)
@authorized_user
async def file_handler(client: Client, message: Message):
    """Handles incoming files, downloads them, and uploads to Wasabi."""
    media = message.document or message.video or message.audio
    if not media:
        await message.reply_text("Unsupported file type.")
        return
    
    file_name = media.file_name or f"file_{message.id}"
    file_size = media.file_size
    
    if file_size > 4 * 1024 * 1024 * 1024:
        await message.reply_text("❌ **Error:** File is larger than the 4GB limit.")
        return

    download_path = f"./downloads/{file_name}"
    os.makedirs(os.path.dirname(download_path), exist_ok=True)

    status_msg = await message.reply_text(f"📥 **Starting download:** `{file_name}`")
    
    start_time = time.time()
    last_update_time = start_time

    # Download progress callback
    async def progress(current, total):
        nonlocal last_update_time
        now = time.time()
        if now - last_update_time > 2.0:
            percentage = (current / total) * 100
            elapsed_time = now - start_time
            speed = current / elapsed_time if elapsed_time > 0 else 0
            progress_str = f"[{'█' * int(percentage / 5)}{'░' * (20 - int(percentage / 5))}]"
            
            text = (
                f"**📥 Downloading from Telegram...**\n\n"
                f"`{progress_str}` **{percentage:.2f}%**\n\n"
                f"✅ **Downloaded:** {humanbytes(current)} / {humanbytes(total)}\n"
                f"⚡️ **Speed:** {humanbytes(speed)}/s\n"
                f"⏳ **Elapsed:** {time_formatter(elapsed_time)}"
            )
            try:
                await status_msg.edit_text(text)
                last_update_time = now
            except Exception as e:
                print(f"Error updating download progress: {e}")

    try:
        await client.download_media(
            message=message,
            file_name=download_path,
            progress=progress
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during download:** {e}")
        if os.path.exists(download_path):
            os.remove(download_path)
        return

    await status_msg.edit_text("✅ **Download complete!**\n\nStarting upload to Wasabi...")

    # Upload to Wasabi with simplified progress
    upload_start_time = time.time()
    last_upload_update = upload_start_time
    uploaded_bytes = 0
    
    def upload_progress_callback(bytes_amount):
        nonlocal uploaded_bytes, last_upload_update
        uploaded_bytes += bytes_amount
        now = time.time()
        if now - last_upload_update > 2.0:
            percentage = (uploaded_bytes / file_size) * 100
            elapsed_time = now - upload_start_time
            speed = uploaded_bytes / elapsed_time if elapsed_time > 0 else 0
            
            progress_str = f"[{'█' * int(percentage / 5)}{'░' * (20 - int(percentage / 5))}]"
            
            text = (
                f"**🚀 Uploading to Wasabi...**\n\n"
                f"`{progress_str}` **{percentage:.2f}%**\n\n"
                f"✅ **Uploaded:** {humanbytes(uploaded_bytes)} / {humanbytes(file_size)}\n"
                f"⚡️ **Speed:** {humanbytes(speed)}/s\n"
                f"⏳ **Elapsed:** {time_formatter(elapsed_time)}"
            )
            
            # Update status message (this will run in a thread, so we use run_coroutine_threadsafe)
            asyncio.run_coroutine_threadsafe(status_msg.edit_text(text), asyncio.get_event_loop())
            last_upload_update = now

    try:
        # Upload file to Wasabi
        s3_client.upload_file(
            download_path,
            WASABI_BUCKET,
            file_name,
            Callback=upload_progress_callback
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during upload:** {e}")
        if os.path.exists(download_path):
            os.remove(download_path)
        return
    finally:
        if os.path.exists(download_path):
            os.remove(download_path)

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
    print("Starting Telegram Wasabi Bot...")
    await app.start()
    print("Bot has started successfully!")
    
    # Get bot info
    me = await app.get_me()
    print(f"Bot username: @{me.username}")
    print(f"Bot ID: {me.id}")
    
    # Send a message to admin that bot is running
    try:
        await app.send_message(ADMIN_ID, "🤖 Bot started successfully!")
    except Exception:
        pass
    
    # Keep the bot running
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Run the bot
    try:
        app.run(main())
    except Exception as e:
        print(f"An error occurred during bot execution: {e}")
