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
from urllib.parse import quote
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
import botocore

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

# Configure Wasabi S3 client
try:
    wasabi_endpoint_url = f'https://s3.{WASABI_REGION}.wasabisys.com'
    
    s3_client = boto3.client(
        's3',
        endpoint_url=wasabi_endpoint_url,
        aws_access_key_id=WASABI_ACCESS_KEY,
        aws_secret_access_key=WASABI_SECRET_KEY,
        region_name=WASABI_REGION,
        config=boto3.session.Config(
            s3={'addressing_style': 'virtual'},
            signature_version='s3v4'
        )
    )
    s3_client.head_bucket(Bucket=WASABI_BUCKET)
    logger.info("Successfully connected to Wasabi bucket")
    
except Exception as e:
    logger.error(f"Wasabi connection failed: {e}")
    try:
        wasabi_endpoint_url = f'https://{WASABI_BUCKET}.s3.{WASABI_REGION}.wasabisys.com'
        s3_client = boto3.client(
            's3',
            endpoint_url=wasabi_endpoint_url,
            aws_access_key_id=WASABI_ACCESS_KEY,
            aws_secret_access_key=WASABI_SECRET_KEY,
            region_name=WASABI_REGION
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
        padding = 4 - (len(encoded_url) % 4)
        if padding != 4:
            encoded_url += '=' * padding
        media_url = base64.urlsafe_b64decode(encoded_url).decode()
        return render_template("player.html", media_type=media_type, media_url=media_url)
    except Exception as e:
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
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
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
    if not size:
        return "0 B"
    power = 1024
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < power:
            return f"{size:.2f} {unit}"
        size /= power
    return f"{size:.2f} TB"

def sanitize_filename(filename):
    filename = re.sub(r'[^a-zA-Z0-9 _.-]', '_', filename)
    filename = filename.replace("/", "_")
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    return filename

def get_user_folder(user_id):
    return f"user_{user_id}"

# ✅ Safe URL wrapper to avoid BUTTON_URL_INVALID
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

# Rate limiting
user_requests = defaultdict(list)

def is_rate_limited(user_id, limit=5, period=60):
    now = datetime.now()
    user_requests[user_id] = [req for req in user_requests[user_id] if now - req < timedelta(seconds=period)]
    if len(user_requests[user_id]) >= limit:
        return True
    user_requests[user_id].append(now)
    return False

# -----------------------------
# Bot Handlers
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_rate_limited(message.from_user.id):
        await message.reply_text("Too many requests. Please try again in a minute.")
        return
    
    await message.reply_text(
        "🚀 Cloud Storage Bot with Web Player\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename> to download files\n"
        "Use /play <filename> to get web player links\n"
        "Use /list to see your files\n"
        "Use /delete <filename> to remove files\n\n"
        "<b>⚡ Extreme Performance Features:</b>\n"
        "• 2GB file size support\n"
        "• Real-time speed monitoring with smoothing\n"
        "• Memory optimization for large files\n"
        "• TCP Keepalive for stable connections\n\n"
        "<b>💎 Owner:</b> Mraprguild\n"
        "<b>📧 Email:</b> mraprguild@gmail.com\n"
        "<b>📱 Telegram:</b> @Sathishkumar33",
    )

# (Other handlers stay the same but now use create_download_keyboard → safe_url)

# -----------------------------
# Flask Server Startup
# -----------------------------
print("Starting Flask server on port 8000...")
Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    print("Starting Wasabi Storage Bot with Web Player...")
    app.run()
