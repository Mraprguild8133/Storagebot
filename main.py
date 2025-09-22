import os
import time
import boto3
import asyncio
import re
import base64
from threading import Thread
from flask import Flask, render_template
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait
from dotenv import load_dotenv
from urllib.parse import quote, urlparse
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
import botocore
import uuid

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WASABI_ACCESS_KEY = os.getenv("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.getenv("WASABI_SECRET_KEY")
WASABI_BUCKET = os.getenv("WASABI_BUCKET")
WASABI_REGION = os.getenv("WASABI_REGION", "us-east-1")
RENDER_URL = os.getenv("RENDER_URL", "http://localhost:8000")
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

# Validate environment variables
missing_vars = []
for var_name, var_value in [
    ("API_ID", API_ID),
    ("API_HASH", API_HASH),
    ("BOT_TOKEN", BOT_TOKEN),
    ("WASABI_ACCESS_KEY", WASABI_ACCESS_KEY),
    ("WASABI_SECRET_KEY", WASABI_SECRET_KEY),
    ("WASABI_BUCKET", WASABI_BUCKET)
]:
    if not var_value:
        missing_vars.append(var_name)

if missing_vars:
    raise Exception(f"Missing environment variables: {', '.join(missing_vars)}")

# Initialize clients
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Configure Wasabi S3 client with retry mechanism
wasabi_endpoint_url = f'https://s3.{WASABI_REGION}.wasabisys.com'

session = boto3.Session(
    aws_access_key_id=WASABI_ACCESS_KEY,
    aws_secret_access_key=WASABI_SECRET_KEY,
    region_name=WASABI_REGION
)

s3_client = session.client(
    's3',
    endpoint_url=wasabi_endpoint_url,
    config=botocore.config.Config(
        retries={'max_attempts': MAX_RETRIES},
        s3={'addressing_style': 'virtual'},
        signature_version='s3v4',
        connect_timeout=REQUEST_TIMEOUT,
        read_timeout=REQUEST_TIMEOUT
    )
)

# Test connection
try:
    s3_client.head_bucket(Bucket=WASABI_BUCKET)
    logger.info("Successfully connected to Wasabi bucket")
except Exception as e:
    logger.error(f"Wasabi connection failed: {e}")
    try:
        # Alternative endpoint format
        wasabi_endpoint_url = f'https://{WASABI_BUCKET}.s3.{WASABI_REGION}.wasabisys.com'
        s3_client = session.client(
            's3',
            endpoint_url=wasabi_endpoint_url,
            config=botocore.config.Config(
                retries={'max_attempts': MAX_RETRIES},
                connect_timeout=REQUEST_TIMEOUT,
                read_timeout=REQUEST_TIMEOUT
            )
        )
        s3_client.head_bucket(Bucket=WASABI_BUCKET)
        logger.info("Successfully connected to Wasabi bucket with alternative endpoint")
    except Exception as alt_e:
        logger.error(f"Alternative connection also failed: {alt_e}")
        raise Exception(f"Could not connect to Wasabi: {alt_e}")

# -----------------------------
# Flask app
# -----------------------------
flask_app = Flask(__name__, template_folder="templates")

@flask_app.route("/")
def index():
    return render_template("index.html")

@flask_app.route("/player/<media_type>/<encoded_url>")
def player(media_type, encoded_url):
    try:
        # Add padding if needed
        padding = len(encoded_url) % 4
        if padding:
            encoded_url += '=' * (4 - padding)
        
        media_url = base64.urlsafe_b64decode(encoded_url).decode()
        
        # Validate URL to prevent potential security issues
        parsed_url = urlparse(media_url)
        if not parsed_url.scheme in ('http', 'https'):
            return "Invalid URL scheme", 400
            
        return render_template("player.html", media_type=media_type, media_url=media_url)
    except Exception as e:
        logger.error(f"Error in player route: {e}")
        return f"Error decoding URL: {str(e)}", 400

@flask_app.route("/about")
def about():
    return render_template("about.html")

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)

# -----------------------------
# Helper Functions
# -----------------------------
MEDIA_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.flv', '.wmv', '.3gp'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac', '.aac', '.wma'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg']
}

def get_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    for file_type, extensions in MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return 'other'

def generate_player_url(filename, presigned_url):
    if not RENDER_URL:
        return None
    file_type = get_file_type(filename)
    if file_type in ['video', 'audio', 'image']:
        encoded_url = base64.urlsafe_b64encode(presigned_url.encode()).decode().rstrip('=')
        return f"{RENDER_URL}/player/{file_type}/{encoded_url}"
    return None

def humanbytes(size):
    if not size or size == 0:
        return "0 B"
    power = 1024
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < power:
            return f"{size:.2f} {unit}"
        size /= power
    return f"{size:.2f} TB"

def sanitize_filename(filename):
    # Keep only alphanumeric, spaces, underscores, dots, and hyphens
    filename = re.sub(r'[^a-zA-Z0-9 _.-]', '_', filename)
    filename = filename.replace("/", "_").replace("\\", "_")
    
    # Limit length but preserve extension
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
        
    return filename

def get_user_folder(user_id):
    return f"user_{user_id}"

def safe_url(url: str) -> str:
    return quote(url, safe=":/?&=%")

def create_download_keyboard(presigned_url, player_url=None):
    keyboard = []
    if player_url:
        keyboard.append([InlineKeyboardButton("🎬 Web Player", url=safe_url(player_url))])
    keyboard.append([InlineKeyboardButton("📥 Direct Download", url=safe_url(presigned_url))])
    return InlineKeyboardMarkup(keyboard)

def create_progress_bar(percentage, length=20):
    filled = int(length * percentage / 100)
    empty = length - filled
    return '█' * filled + '○' * empty

def format_eta(seconds):
    if seconds <= 0:
        return "00:00"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    return f"{int(minutes):02d}:{int(seconds):02d}"

def format_elapsed(seconds):
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"

# Improved rate limiting with expiration
user_requests = defaultdict(list)

def is_rate_limited(user_id, limit=5, period=60):
    now = datetime.now()
    # Clean up old requests
    user_requests[user_id] = [req for req in user_requests[user_id] if now - req < timedelta(seconds=period)]
    
    if len(user_requests[user_id]) >= limit:
        return True
        
    user_requests[user_id].append(now)
    return False

# S3 operations with retry logic
async def upload_to_s3(file_path, s3_key):
    for attempt in range(MAX_RETRIES):
        try:
            s3_client.upload_file(
                file_path, 
                WASABI_BUCKET, 
                s3_key,
                ExtraArgs={
                    'ACL': 'private',
                    'ContentType': 'application/octet-stream'
                }
            )
            return True
        except Exception as e:
            logger.error(f"Upload attempt {attempt + 1} failed: {e}")
            if attempt == MAX_RETRIES - 1:
                return False
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    return False

def generate_presigned_url(s3_key, expiration=3600):
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': WASABI_BUCKET, 'Key': s3_key},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        return None

# -----------------------------
# Bot Handlers
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_rate_limited(message.from_user.id):
        await message.reply_text("🚫 Too many requests. Please try again in a minute.")
        return
    
    welcome_text = """
🚀 Cloud Storage Bot with Web Player

Send me any file to upload to Wasabi storage
Use /download <filename> to download files
Use /play <filename> to get web player links
Use /list to see your files
Use /delete <filename> to remove files

<b>⚡ Extreme Performance Features:</b>
• 2GB file size support
• Real-time speed monitoring with smoothing
• Memory optimization for large files
• TCP Keepalive for stable connections

<b>💎 Owner:</b> Mraprguild
<b>📧 Email:</b> mraprguild@gmail.com
<b>📱 Telegram:</b> @Sathishkumar33
"""
    await message.reply_text(welcome_text)

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def handle_media(client, message: Message):
    user_id = message.from_user.id
    if is_rate_limited(user_id, limit=3, period=60):
        await message.reply_text("🚫 Too many uploads. Please wait a minute.")
        return
    
    try:
        # Determine file details
        if message.document:
            file_size = message.document.file_size
            file_name = message.document.file_name
        elif message.video:
            file_size = message.video.file_size
            file_name = f"video_{message.video.file_unique_id}.mp4"
        elif message.audio:
            file_size = message.audio.file_size
            file_name = f"audio_{message.audio.file_unique_id}.mp3"
        elif message.photo:
            file_size = message.photo.file_size
            file_name = f"photo_{message.photo.file_unique_id}.jpg"
        else:
            await message.reply_text("❌ Unsupported file type.")
            return
            
        # Check file size
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large. Maximum size is {humanbytes(MAX_FILE_SIZE)}.")
            return
            
        # Notify user
        progress_msg = await message.reply_text(f"📤 Downloading {file_name}...")
        
        # Download file
        download_path = await message.download()
        if not download_path:
            await progress_msg.edit_text("❌ Failed to download file.")
            return
            
        # Prepare for upload
        sanitized_name = sanitize_filename(file_name)
        user_folder = get_user_folder(user_id)
        s3_key = f"{user_folder}/{sanitized_name}"
        
        await progress_msg.edit_text(f"☁️ Uploading to cloud storage...")
        
        # Upload to S3
        success = await upload_to_s3(download_path, s3_key)
        
        # Clean up local file
        try:
            os.remove(download_path)
        except:
            pass
            
        if not success:
            await progress_msg.edit_text("❌ Failed to upload file to cloud storage.")
            return
            
        # Generate shareable links
        presigned_url = generate_presigned_url(s3_key)
        player_url = generate_player_url(file_name, presigned_url)
        
        # Send success message
        file_size_str = humanbytes(file_size)
        success_text = f"✅ Upload successful!\n\n📁 File: {sanitized_name}\n📦 Size: {file_size_str}"
        
        keyboard = create_download_keyboard(presigned_url, player_url)
        await progress_msg.edit_text(success_text, reply_markup=keyboard)
        
    except FloodWait as e:
        await message.reply_text(f"⏳ Flood wait: Please wait {e.value} seconds.")
    except Exception as e:
        logger.error(f"Error handling media: {e}")
        await message.reply_text("❌ An error occurred while processing your file.")

# Add other handlers for /download, /list, /delete, etc.

# -----------------------------
# Flask Server Startup
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask server on port 8000...")
    Thread(target=run_flask, daemon=True).start()
    
    print("Starting Wasabi Storage Bot with Web Player...")
    app.run()
