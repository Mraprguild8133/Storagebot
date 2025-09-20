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
from dotenv import load_dotenv
from urllib.parse import quote
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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

# Validate environment variables
missing_vars = []
for var_name, var_value in [
    ("API_ID", API_ID),
    ("API_HASH", API_HASH),
    ("BOT_TOKEN", BOT_TOKEN),
    ("WASABI_ACCESS_KEY", WASABI_ACCESS_KEY),
    ("WASABI_SECRET_KEY", WASABI_SECRET_KEY),
    ("WASABI_BUCKET", WASABI_BUCKET),
]:
    if not var_value:
        missing_vars.append(var_name)

if missing_vars:
    raise Exception(f"Missing environment variables: {', '.join(missing_vars)}")

# Initialize Pyrogram client
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Configure Wasabi S3 client
wasabi_endpoint_url = f"https://s3.{WASABI_REGION}.wasabisys.com"
s3_client = boto3.client(
    "s3",
    endpoint_url=wasabi_endpoint_url,
    aws_access_key_id=WASABI_ACCESS_KEY,
    aws_secret_access_key=WASABI_SECRET_KEY,
    region_name=WASABI_REGION,
)

# -----------------------------
# Flask app for player.html
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
            encoded_url += "=" * padding
        media_url = base64.urlsafe_b64decode(encoded_url).decode()
        return render_template("player.html", media_type=media_type, media_url=media_url)
    except Exception as e:
        return f"Error decoding URL: {str(e)}", 400

@flask_app.route("/about")
def about():
    return render_template("about.html")

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)

# -----------------------------
# Helpers
# -----------------------------
MEDIA_EXTENSIONS = {
    "video": [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"],
    "audio": [".mp3", ".m4a", ".ogg", ".wav", ".flac"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
}

def get_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    for file_type, extensions in MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return "other"

def generate_player_url(filename, presigned_url):
    if not RENDER_URL:
        return None
    file_type = get_file_type(filename)
    if file_type in ["video", "audio", "image"]:
        encoded_url = base64.urlsafe_b64encode(presigned_url.encode()).decode().rstrip("=")
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
    filename = re.sub(r"[^a-zA-Z0-9 _.-]", "_", filename)
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200 - len(ext)] + ext
    return filename

def get_user_folder(user_id):
    return f"user_{user_id}"

def create_download_keyboard(presigned_url, player_url=None):
    keyboard = []
    if player_url:
        keyboard.append([InlineKeyboardButton("🎬 Web Player", url=player_url)])
    keyboard.append([InlineKeyboardButton("📥 Direct Download", url=presigned_url)])
    return InlineKeyboardMarkup(keyboard)

# -----------------------------
# Progress Functions
# -----------------------------
async def progress_for_pyrogram(current, total, message, start_time, prefix="Downloading"):
    now = time.time()
    diff = now - start_time
    if diff == 0:
        diff = 0.001
    speed = current / diff
    percentage = current * 100 / total
    eta = (total - current) / speed if speed > 0 else 0

    progress_str = "█" * int(percentage // 5) + "○" * (20 - int(percentage // 5))
    text = (
        f"{prefix}\n"
        f"[{progress_str}] {percentage:.1f}%\n"
        f"Processed: {humanbytes(current)} of {humanbytes(total)}\n"
        f"Speed: {humanbytes(speed)}/s | ETA: {int(eta)}s\n"
        f"Elapsed: {int(diff)}s"
    )
    try:
        await message.edit_text(text)
    except Exception:
        pass

# -----------------------------
# Bot Handlers
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "🚀 Cloud Storage Bot with Web Player\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename> to download files\n"
        "Use /play <filename> to get web player links\n"
        "Use /list to see your files\n"
        "Use /delete <filename> to remove files"
    )

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    media = message.document or message.video or message.audio or message.photo
    if not media:
        await message.reply_text("Unsupported file type")
        return

    status_message = await message.reply_text("Downloading file...")
    start_time = time.time()

    try:
        # Telegram → Local
        file_path = await message.download(
            progress=lambda c, t: asyncio.create_task(
                progress_for_pyrogram(c, t, status_message, start_time, "Downloading")
            )
        )
        file_name = sanitize_filename(os.path.basename(file_path))
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"

        # Local → Wasabi (default single-threaded)
        await asyncio.to_thread(
            s3_client.upload_file,
            Filename=file_path,
            Bucket=WASABI_BUCKET,
            Key=user_file_name
        )

        presigned_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": WASABI_BUCKET, "Key": user_file_name},
            ExpiresIn=86400,
        )

        player_url = generate_player_url(file_name, presigned_url)
        keyboard = create_download_keyboard(presigned_url, player_url)

        file_size = media.file_size if hasattr(media, "file_size") else 0
        if message.photo:
            file_size = os.path.getsize(file_path)

        response_text = (
            f"✅ Upload complete!\n\n📁 File: {file_name}\n"
            f"📦 Size: {humanbytes(file_size)}\n"
            f"⏰ Link expires: 24 hours"
        )
        if player_url:
            response_text += f"\n\n🎬 Web Player: {player_url}"

        await status_message.edit_text(response_text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if "file_path" in locals() and os.path.exists(file_path):
            os.remove(file_path)

# -----------------------------
# Flask Server Startup
# -----------------------------
print("Starting Flask server on port 8000...")
Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    print("Starting Wasabi Storage Bot with Web Player...")
    app.run()
