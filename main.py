import os
import re
import base64
import asyncio
import time
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import aiofiles
import aiohttp

import boto3
from dotenv import load_dotenv
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler

from flask import Flask, render_template, request, jsonify
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
    "MAX_WORKERS": os.getenv("4"),
    "CHUNK_SIZE": os.getenv("131072"),
}

missing_vars = [var for var, value in required_env_vars.items() if not value and var not in ["RENDER_URL", "MAX_WORKERS", "CHUNK_SIZE"]]
if missing_vars:
    raise Exception(f"Missing environment variables: {', '.join(missing_vars)}")

# -----------------------------
# Initialize Pyrogram Client with optimization
# -----------------------------
app = Client(
    "wasabi_bot",
    api_id=required_env_vars["API_ID"],
    api_hash=required_env_vars["API_HASH"],
    bot_token=required_env_vars["BOT_TOKEN"],
    workers=int(required_env_vars["MAX_WORKERS"]),
    max_concurrent_transmissions=5,
    sleep_threshold=30,
)

# -----------------------------
# Initialize Wasabi S3 client with optimization
# -----------------------------
wasabi_endpoint_url = f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com'
session = boto3.Session()
s3_client = session.client(
    's3',
    endpoint_url=wasabi_endpoint_url,
    aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
    aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"],
    config=boto3.session.Config(
        max_pool_connections=50,
        retries={'max_attempts': 3},
        connect_timeout=30,
        read_timeout=30,
    )
)

# Thread pool for concurrent operations
thread_pool = ThreadPoolExecutor(max_workers=int(required_env_vars["MAX_WORKERS"]))

# -----------------------------
# Flask app for player.html
# -----------------------------
flask_app = Flask(__name__, template_folder="templates")

@flask_app.route("/")
def index():
    return render_template("index.html")

@flask_app.route("/player/<media_type>/<encoded_url>")
def player(media_type, encoded_url):
    # Decode the URL
    try:
        # Add padding if needed
        padding = 4 - (len(encoded_url) % 4)
        if padding != 4:
            encoded_url += '=' * padding
        media_url = base64.urlsafe_b64decode(encoded_url).decode()
        return render_template("player.html", media_type=media_type, media_url=media_url)
    except Exception as e:
        return f"Error decoding URL: {str(e)}", 400

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok"})

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)

# -----------------------------
# Constants & Helpers
# -----------------------------
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB
CHUNK_SIZE = int(required_env_vars["CHUNK_SIZE"])
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MEDIA_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.flv', '.wmv'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac', '.aac', '.wma'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff']
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
        self.speeds = []
        self.update_interval = 0.5
        
    async def update(self, downloaded):
        current_time = time.time()
        self.downloaded = downloaded
        
        time_diff = current_time - self.last_update_time
        if time_diff >= self.update_interval:
            downloaded_diff = downloaded - self.last_downloaded
            current_speed = downloaded_diff / time_diff
            self.speeds.append(current_speed)
            
            if len(self.speeds) > 5:
                self.speeds.pop(0)
            self.speed = sum(self.speeds) / len(self.speeds)
            
            if self.speed > 0:
                remaining = self.total_size - downloaded
                self.eta = humantime(remaining / self.speed)
            else:
                self.eta = "Unknown"
            
            progress_percent = (downloaded / self.total_size) * 100
            progress_bar = self.get_progress_bar(progress_percent)
            
            media = self.message.document or self.message.video or self.message.audio or self.message.photo
            filename = getattr(media, "file_name", "Unknown")
            
            status_text = (
                f"📥 Downloading...\n\n"
                f"File: {filename}\n"
                f"Progress: {progress_bar} {progress_percent:.1f}%\n"
                f"Downloaded: {humanbytes(downloaded)} / {humanbytes(self.total_size)}\n"
                f"Speed: {humanbytes(self.speed)}/s\n"
                f"ETA: {self.eta}"
            )
            
            try:
                await self.status_message.edit_text(status_text)
            except FloodWait as e:
                self.update_interval = min(5.0, self.update_interval + 0.5)
                await asyncio.sleep(e.value)
            except:
                pass
            
            self.last_update_time = current_time
            self.last_downloaded = downloaded
    
    def get_progress_bar(self, percent, length=10):
        filled = int(length * percent / 100)
        return "█" * filled + "░" * (length - filled)

# -----------------------------
# Download Function
# -----------------------------
async def download_file_with_progress(client, message, file_path, progress_callback=None):
    return await client.download_media(
        message,
        file_name=file_path,
        progress=progress_callback,
        block=True
    )

# -----------------------------
# Upload Function
# -----------------------------
async def upload_to_wasabi(file_path, bucket, key):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        thread_pool,
        lambda: s3_client.upload_file(
            file_path,
            bucket,
            key,
            Config=boto3.s3.transfer.TransferConfig(
                multipart_threshold=8 * 1024 * 1024,
                max_concurrency=10,
                use_threads=True
            )
        )
    )

# -----------------------------
# List Files Function
# -----------------------------
async def list_user_files(user_id):
    user_folder = get_user_folder(user_id)
    loop = asyncio.get_event_loop()
    
    try:
        response = await loop.run_in_executor(
            thread_pool,
            lambda: s3_client.list_objects_v2(
                Bucket=required_env_vars["WASABI_BUCKET"],
                Prefix=user_folder + "/"
            )
        )
        
        if 'Contents' in response:
            files = []
            for obj in response['Contents']:
                if obj['Key'] != user_folder + '/':  # Skip the folder itself
                    filename = obj['Key'].split('/')[-1]
                    filesize = humanbytes(obj['Size'])
                    last_modified = obj['LastModified'].strftime("%Y-%m-%d %H:%M:%S")
                    files.append({
                        'name': filename,
                        'size': filesize,
                        'last_modified': last_modified
                    })
            return files
        return []
    except Exception as e:
        print(f"Error listing files: {e}")
        return []

# -----------------------------
# Generate Presigned URL
# -----------------------------
async def generate_presigned_url(bucket, key):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        thread_pool,
        lambda: s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=86400
        )
    )

# -----------------------------
# Telegram Bot Handlers
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    welcome_text = (
        "🚀 **High-Speed Cloud Storage Bot**\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "• Optimized for maximum download/upload speed\n"
        "• Parallel processing for faster operations\n"
        "• Real-time progress with speed indicators\n\n"
        "Commands:\n"
        "/download <filename> - Download a file\n"
        "/list - List your files\n"
        "/play <filename> - Get a web player link for media files\n\n"
        "⚠️ Maximum file size: 2GB"
    )
    if required_env_vars["RENDER_URL"]:
        welcome_text += "\n\n🎥 Web player support is enabled!"
    await message.reply_text(welcome_text)

@app.on_message(filters.command("list"))
async def list_files_command(client, message: Message):
    status_message = await message.reply_text("📋 Fetching your files...")
    
    try:
        files = await list_user_files(message.from_user.id)
        
        if not files:
            await status_message.edit_text("You don't have any files stored yet.")
            return
        
        response_text = "📁 Your Files:\n\n"
        for i, file_info in enumerate(files, 1):
            response_text += f"{i}. {file_info['name']}\n"
            response_text += f"   Size: {file_info['size']}\n"
            response_text += f"   Uploaded: {file_info['last_modified']}\n\n"
        
        # Split if message is too long
        if len(response_text) > 4000:
            parts = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
            for part in parts:
                await message.reply_text(part)
            await status_message.delete()
        else:
            await status_message.edit_text(response_text)
            
    except Exception as e:
        await status_message.edit_text(f"❌ Error listing files: {str(e)}")

@app.on_message(filters.command("download"))
async def download_file_command(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Please specify a filename. Usage: /download <filename>")
        return
    
    filename = " ".join(message.command[1:])
    user_folder = get_user_folder(message.from_user.id)
    file_key = f"{user_folder}/{filename}"
    
    status_message = await message.reply_text(f"🔍 Looking for file: {filename}")
    
    try:
        # Check if file exists
        await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            lambda: s3_client.head_object(
                Bucket=required_env_vars["WASABI_BUCKET"],
                Key=file_key
            )
        )
        
        # Generate presigned URL
        presigned_url = await generate_presigned_url(required_env_vars["WASABI_BUCKET"], file_key)
        
        await status_message.edit_text(
            f"✅ File found: {filename}\n\n"
            f"Download Link: {presigned_url}\n\n"
            f"⚠️ This link will expire in 24 hours."
        )
        
    except Exception as e:
        await status_message.edit_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("play"))
async def play_file_command(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Please specify a filename. Usage: /play <filename>")
        return
    
    filename = " ".join(message.command[1:])
    user_folder = get_user_folder(message.from_user.id)
    file_key = f"{user_folder}/{filename}"
    
    status_message = await message.reply_text(f"🔍 Looking for file: {filename}")
    
    try:
        # Check if file exists
        await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            lambda: s3_client.head_object(
                Bucket=required_env_vars["WASABI_BUCKET"],
                Key=file_key
            )
        )
        
        # Generate presigned URL
        presigned_url = await generate_presigned_url(required_env_vars["WASABI_BUCKET"], file_key)
        
        # Generate player URL
        player_url = generate_player_url(filename, presigned_url)
        
        if player_url:
            await status_message.edit_text(
                f"🎮 Player URL for {filename}:\n\n{player_url}\n\n"
                f"Open this URL in your browser to play the media."
            )
        else:
            await status_message.edit_text(
                f"❌ File type not supported for playback: {filename}\n\n"
                f"Direct Download Link: {presigned_url}\n\n"
                f"⚠️ This link will expire in 24 hours."
            )
        
    except Exception as e:
        await status_message.edit_text(f"❌ Error: {str(e)}")

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

    # Get filename
    filename = getattr(media, "file_name", None)
    if not filename:
        if message.document:
            filename = "document"
        elif message.video:
            filename = "video"
        elif message.audio:
            filename = "audio"
        elif message.photo:
            filename = "photo"
        # Add extension based on media type
        if hasattr(media, "mime_type") and media.mime_type:
            ext = media.mime_type.split("/")[-1]
            filename = f"{filename}.{ext}"

    status_message = await message.reply_text("📥 Initializing high-speed download...")

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
        file_name = sanitize_filename(filename)
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        
        await download_file_with_progress(client, message, file_path, progress_callback)
        
        await status_message.edit_text("📤 Uploading to Wasabi with high-speed transfer...")
        
        # Upload to Wasabi
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
        await upload_to_wasabi(file_path, required_env_vars["WASABI_BUCKET"], user_file_name)

        # Generate presigned URL
        presigned_url = await generate_presigned_url(required_env_vars["WASABI_BUCKET"], user_file_name)

        player_url = generate_player_url(file_name, presigned_url)

        response_text = (
            f"✅ Upload complete!\n\n"
            f"File: {file_name}\n"
            f"Size: {humanbytes(size) if size else 'N/A'}\n"
            f"Direct Link: {presigned_url}"
        )

        # Add player URL to response if available
        if player_url:
            response_text += f"\n\nPlayer URL: {player_url}"

        await status_message.edit_text(response_text)

    except Exception as e:
        print("Error:", traceback.format_exc())
        await status_message.edit_text(f"❌ Error: {str(e)}")
    finally:
        try:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
        except (FileNotFoundError, PermissionError):
            pass

# -----------------------------
# Run Both Flask + Bot
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask server on port 8000...")
    Thread(target=run_flask, daemon=True).start()

    print("Starting High-Speed Wasabi Storage Bot...")
    print(f"Optimization settings:")
    print(f"- Max workers: {required_env_vars['4']}")
    print(f"- Chunk size: {humanbytes(131072)}")
    print(f"- Max concurrent transmissions: 5")
    
    app.run()
