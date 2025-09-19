import os
import re
import base64
import asyncio
import time
import traceback
from pathlib import Path
from datetime import datetime
from threading import Thread

import boto3
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import BadRequest

from flask import Flask, render_template

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
# Flask app for player.html and index.html
# -----------------------------
flask_app = Flask(__name__, template_folder="templates")

@flask_app.route("/")
def index():
    bot_username = os.getenv("BOT_USERNAME", "your_bot_username")
    return render_template("index.html", bot_username=bot_username, render_url=required_env_vars["RENDER_URL"])

@flask_app.route("/player/<media_type>/<encoded_url>")
def player(media_type, encoded_url):
    return render_template("player.html", media_type=media_type, encoded_url=encoded_url)

@flask_app.route("/about")
def about():
    return render_template("about.html")

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
        return f"{seconds:.0f}s"
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

def progress_bar(percentage, length=20):
    filled = int(length * percentage / 100)
    empty = length - filled
    return "█" * filled + "░" * empty

# -----------------------------
# Async-safe Download Progress
# -----------------------------
class DownloadProgress:
    def __init__(self, total_size, message):
        self.total_size = total_size or 0
        self.downloaded = 0
        self.start_time = time.time()
        self.last_update = 0
        self.message = message
        self.speed = 0
        self.eta = "Calculating..."

    def update(self, current):
        now = time.time()
        self.downloaded = current
        if now - self.last_update >= 1:  # update every 1 second
            elapsed = now - self.start_time
            self.speed = self.downloaded / elapsed if elapsed > 0 else 0
            self.eta = humantime((self.total_size - self.downloaded) / self.speed) if self.speed > 0 else "∞"
            self.last_update = now
            return True
        return False

    def get_text(self, filename):
        progress_percent = (self.downloaded / self.total_size) * 100 if self.total_size else 0
        bar = progress_bar(progress_percent)
        return (
            f"📥 Downloading...\n\n"
            f"File: {filename}\n"
            f"Progress: {bar} {progress_percent:.1f}%\n"
            f"Downloaded: {humanbytes(self.downloaded)} / {humanbytes(self.total_size)}\n"
            f"Speed: {humanbytes(self.speed)}/s\n"
            f"ETA: {self.eta}"
        )

# -----------------------------
# Async-safe file download
# -----------------------------
async def download_file(client, message, progress: DownloadProgress):
    media = message.document or message.video or message.audio or message.photo
    filename = getattr(media, "file_name", "File")
    size = getattr(media, "file_size", None)
    progress.total_size = size or 0

    status_msg = await message.reply_text(progress.get_text(filename))
    progress.message = status_msg

    def progress_callback(current, total):
        progress.update(current)
        asyncio.create_task(progress.message.edit_text(progress.get_text(filename)))

    file_path = await client.download_media(
        message,
        file_name=DOWNLOAD_DIR / sanitize_filename(filename),
        progress=progress_callback
    )
    return file_path, filename

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
        welcome_text += f"\n\n🌐 Web Interface: {required_env_vars['RENDER_URL']}"
    await message.reply_text(welcome_text)

@app.on_message(filters.command("web"))
async def web_command(client, message: Message):
    if required_env_vars["RENDER_URL"]:
        await message.reply_text(f"🌐 Web Interface: {required_env_vars['RENDER_URL']}")
    else:
        await message.reply_text("Web interface is not configured.")

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    media = message.document or message.video or message.audio or message.photo
    size = getattr(media, "file_size", None)

    if size and size > MAX_FILE_SIZE:
        await message.reply_text(f"File too large. Max size: {humanbytes(MAX_FILE_SIZE)}")
        return

    progress = DownloadProgress(size, None)

    try:
        # Download
        file_path, filename = await download_file(client, message, progress)

        final_file_name = sanitize_filename(filename)
        user_file_name = f"{get_user_folder(message.from_user.id)}/{final_file_name}"

        # Upload to Wasabi (blocking call in thread)
        status_msg = await message.reply_text("📤 Uploading to Wasabi...")
        await asyncio.to_thread(
            s3_client.upload_file,
            file_path,
            required_env_vars["WASABI_BUCKET"],
            user_file_name
        )

        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
            ExpiresIn=86400
        )

        player_url = generate_player_url(final_file_name, presigned_url)

        response_text = (
            f"✅ Upload complete!\n\n"
            f"File: {final_file_name}\n"
            f"Size: {humanbytes(size) if size else 'N/A'}\n"
            f"Direct Link: {presigned_url}"
        )
        if player_url:
            response_text += f"\n\nPlayer URL: {player_url}"
        if required_env_vars["RENDER_URL"]:
            response_text += f"\n\n🌐 Web Interface: {required_env_vars['RENDER_URL']}"

        await status_msg.edit_text(response_text)

    except Exception as e:
        print("Error:", traceback.format_exc())
        await message.reply_text(f"Error: {str(e)}")
    finally:
        try:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass

# -----------------------------
# Run Both Flask + Bot
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask server on port 8000...")
    Thread(target=run_flask, daemon=True).start()

    print("Starting Wasabi Storage Bot...")
    app.run()
    
