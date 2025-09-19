import os
import re
import base64
import asyncio
import time
import traceback
from pathlib import Path
from datetime import datetime, timedelta

import boto3
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message

from flask import Flask, render_template
from threading import Thread

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

required_env_vars = {
    "API_ID": os.getenv("API_ID"),
    "API_HASH": os.getenv("API_HASH"),
    "BOT_TOKEN": os.getenv("BOT_TOKEN"),
    "WASABI_ACCESS_KEY": os.getenv("WASABI_ACCESS_KEY"),
    "WASABI_SECRET_KEY": os.getenv("WASABI_SECRET_KEY"),
    "WASABI_BUCKET": os.getenv("WASABI_BUCKET"),
    "WASABI_REGION": os.getenv("WASABI_REGION"),
    "RENDER_URL": os.getenv("RENDER_URL", "").rstrip('/'),
}

missing_vars = [var for var, value in required_env_vars.items() if not value and var != "RENDER_URL"]
if missing_vars:
    raise Exception(f"Missing environment variables: {', '.join(missing_vars)}")

# -----------------------------
# Initialize Pyrogram Client
# -----------------------------
app = Client(
    "wasabi_bot",
    api_id=required_env_vars["API_ID"],
    api_hash=required_env_vars["API_HASH"],
    bot_token=required_env_vars["BOT_TOKEN"]
)

# -----------------------------
# Initialize Wasabi S3 client
# -----------------------------
wasabi_endpoint_url = f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com'
s3_client = boto3.client(
    's3',
    endpoint_url=wasabi_endpoint_url,
    aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
    aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"]
)

# -----------------------------
# Flask app for player.html
# -----------------------------
flask_app = Flask(__name__, template_folder="templates")

@flask_app.route("/player/<media_type>/<encoded_url>")
def player(media_type, encoded_url):
    return render_template("player.html", media_type=media_type, encoded_url=encoded_url)

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)

# -----------------------------
# Constants & Helpers
# -----------------------------
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MEDIA_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
}

def humanbytes(size):
    if not size:
        return "0 B"
    power = 1024
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < power:
            return f"{size:.2f} {unit}"
        size /= power
    return f"{size:.2f} TB"

def humantime(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds // 60:.0f}m {seconds % 60:.0f}s"
    else:
        return f"{seconds // 3600:.0f}h {(seconds % 3600) // 60:.0f}m"

def get_user_folder(user_id):
    return f"user_{user_id}"

def sanitize_filename(filename, max_length=150):
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return filename[:max_length]

def get_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    for file_type, extensions in MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return 'other'

def generate_player_url(filename, presigned_url):
    if not required_env_vars["RENDER_URL"]:
        return None
    file_type = get_file_type(filename)
    if file_type in ['video', 'audio', 'image']:
        encoded_url = base64.urlsafe_b64encode(presigned_url.encode()).decode().rstrip('=')
        return f"{required_env_vars['RENDER_URL']}/player/{file_type}/{encoded_url}"
    return None

# -----------------------------
# Progress Tracker Class
# -----------------------------
class ProgressTracker:
    def __init__(self, total_size, message, status_message):
        self.total_size = total_size
        self.message = message
        self.status_message = status_message
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.downloaded = 0
        self.last_downloaded = 0
        self.speed = 0
        self.eta = "Calculating..."
        
    async def update(self, downloaded):
        current_time = time.time()
        self.downloaded = downloaded
        
        # Calculate speed (bytes per second)
        time_diff = current_time - self.last_update_time
        if time_diff >= 1.0:  # Update at most once per second
            downloaded_diff = downloaded - self.last_downloaded
            self.speed = downloaded_diff / time_diff
            
            # Calculate ETA
            if self.speed > 0:
                remaining = self.total_size - downloaded
                self.eta = humantime(remaining / self.speed)
            else:
                self.eta = "Unknown"
            
            # Update status message
            progress_percent = (downloaded / self.total_size) * 100
            progress_bar = self.get_progress_bar(progress_percent)
            
            status_text = (
                f"📥 Downloading...\n\n"
                f"File: {self.message.document.file_name if self.message.document else 'Unknown'}\n"
                f"Progress: {progress_bar} {progress_percent:.1f}%\n"
                f"Downloaded: {humanbytes(downloaded)} / {humanbytes(self.total_size)}\n"
                f"Speed: {humanbytes(self.speed)}/s\n"
                f"ETA: {self.eta}"
            )
            
            try:
                await self.status_message.edit_text(status_text)
            except:
                pass  # Avoid spamming if message edits happen too quickly
            
            self.last_update_time = current_time
            self.last_downloaded = downloaded
    
    def get_progress_bar(self, percent, length=10):
        filled = int(length * percent / 100)
        return "█" * filled + "░" * (length - filled)

# -----------------------------
# Telegram Bot Handlers
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    welcome_text = (
        "🚀 **Cloud Storage Bot**\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename> to download files\n"
        "Use /list to see your files\n"
        "Use /play <filename> to get a web player link (for media files)\n\n"
        "⚠️ Maximum file size: 2GB"
    )
    if required_env_vars["RENDER_URL"]:
        welcome_text += "\n\n🎥 Web player support is enabled!"
    await message.reply_text(welcome_text)

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    media = message.document or message.video or message.audio or message.photo
    if not media:
        await message.reply_text("Unsupported file type")
        return

    size = getattr(media, "file_size", None)
    if size and size > MAX_FILE_SIZE:
        await message.reply_text(f"File too large. Maximum size is {humanbytes(MAX_FILE_SIZE)}")
        return

    status_message = await message.reply_text("📥 Downloading file...\n\nInitializing...")

    try:
        # Create progress tracker
        progress_tracker = ProgressTracker(size, message, status_message)
        
        # Define progress callback
        def progress_callback(current, total):
            asyncio.run_coroutine_threadsafe(
                progress_tracker.update(current),
                asyncio.get_event_loop()
            )
        
        # Download file with progress tracking
        file_path = await message.download(progress=progress_callback)
        file_name = sanitize_filename(os.path.basename(file_path))
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"

        await status_message.edit_text("📤 Uploading to Wasabi...")
        
        # Upload to Wasabi
        await asyncio.to_thread(
            s3_client.upload_file,
            file_path,
            required_env_vars["WASABI_BUCKET"],
            user_file_name
        )

        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
            ExpiresIn=86400
        )

        player_url = generate_player_url(file_name, presigned_url)

        response_text = (
            f"✅ Upload complete!\n\n"
            f"File: {file_name}\n"
            f"Size: {humanbytes(size) if size else 'N/A'}\n"
            f"Direct Link: {presigned_url}"
        )

        # Add player URL to response if available (as text, not button)
        if player_url:
            response_text += f"\n\nPlayer URL: {player_url}"

        await status_message.edit_text(response_text)

    except Exception as e:
        print("Error:", traceback.format_exc())
        await status_message.edit_text(f"❌ Error: {str(e)}")
    finally:
        try:
            if 'file_path' in locals():
                os.remove(file_path)
        except FileNotFoundError:
            pass

# -----------------------------
# Run Both Flask + Bot
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask server on port 8000...")
    Thread(target=run_flask, daemon=True).start()

    print("Starting Wasabi Storage Bot...")
    app.run()
