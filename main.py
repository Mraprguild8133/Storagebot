import os
import re
import base64
import asyncio
import traceback
from pathlib import Path

import boto3
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message

from flask import Flask, render_template, jsonify
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

def get_user_folder(user_id):
    return f"user_{user_id}"

def sanitize_filename(filename, max_length=150):
    # Keep only alphanumeric, spaces, dots, hyphens, and underscores
    filename = re.sub(r'[^\w\s.-]', '', filename)
    # Replace spaces with underscores
    filename = re.sub(r'\s+', '_', filename)
    # Limit length
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
    # Check if user is authorized
    if not message.from_user:
        await message.reply_text("Cannot identify user.")
        return

    media = message.document or message.video or message.audio or message.photo
    if not media:
        await message.reply_text("Unsupported file type")
        return

    # Get filename
    if hasattr(media, 'file_name') and media.file_name:
        file_name = media.file_name
    elif message.photo:
        file_name = f"photo_{message.id}.jpg"
    else:
        file_name = "unknown_file"
    
    file_name = sanitize_filename(file_name)

    size = getattr(media, "file_size", None)
    if size and size > MAX_FILE_SIZE:
        await message.reply_text(f"File too large. Maximum size is {humanbytes(MAX_FILE_SIZE)}")
        return

    status_message = await message.reply_text("Downloading file...")

    try:
        file_path = await message.download(file_name=DOWNLOAD_DIR / file_name)
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"

        await status_message.edit_text("Uploading to Wasabi storage...")
        
        await asyncio.to_thread(
            s3_client.upload_file,
            str(file_path),
            required_env_vars["WASABI_BUCKET"],
            user_file_name
        )

        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
            ExpiresIn=86400  # 24 hours
        )

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
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        try:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file: {e}")

# -----------------------------
# Additional Bot Commands
# -----------------------------
@app.on_message(filters.command("list"))
async def list_files(client, message: Message):
    try:
        user_folder = get_user_folder(message.from_user.id)
        response = s3_client.list_objects_v2(
            Bucket=required_env_vars["WASABI_BUCKET"],
            Prefix=user_folder + "/"
        )
        
        if 'Contents' not in response:
            await message.reply_text("You haven't uploaded any files yet.")
            return
        
        files = [obj['Key'].replace(f"{user_folder}/", "") for obj in response['Contents']]
        
        if not files:
            await message.reply_text("You haven't uploaded any files yet.")
            return
            
        files_list = "\n".join([f"• {file}" for file in files])
        await message.reply_text(f"Your files:\n\n{files_list}")
        
    except Exception as e:
        await message.reply_text(f"Error listing files: {str(e)}")

@app.on_message(filters.command("download"))
async def download_file(client, message: Message):
    try:
        if len(message.command) < 2:
            await message.reply_text("Please specify a filename. Usage: /download filename")
            return
            
        filename = " ".join(message.command[1:])
        user_folder = get_user_folder(message.from_user.id)
        user_file_name = f"{user_folder}/{filename}"
        
        # Generate a presigned URL for downloading
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
            ExpiresIn=3600  # 1 hour
        )
        
        await message.reply_text(
            f"Download link for {filename}:\n\n{presigned_url}\n\n"
            "This link will expire in 1 hour."
        )
        
    except Exception as e:
        await message.reply_text(f"Error generating download link: {str(e)}")

@app.on_message(filters.command("play"))
async def play_file(client, message: Message):
    try:
        if len(message.command) < 2:
            await message.reply_text("Please specify a filename. Usage: /play filename")
            return
            
        filename = " ".join(message.command[1:])
        user_folder = get_user_folder(message.from_user.id)
        user_file_name = f"{user_folder}/{filename}"
        
        # Check if file exists
        try:
            s3_client.head_object(
                Bucket=required_env_vars["WASABI_BUCKET"],
                Key=user_file_name
            )
        except:
            await message.reply_text("File not found.")
            return
        
        # Generate a presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
            ExpiresIn=86400  # 24 hours
        )
        
        player_url = generate_player_url(filename, presigned_url)
        
        if player_url:
            await message.reply_text(
                f"Player link for {filename}:\n\n{player_url}\n\n"
                "This link will expire in 24 hours."
            )
        else:
            await message.reply_text("This file type doesn't support web playback.")
        
    except Exception as e:
        await message.reply_text(f"Error generating player link: {str(e)}")

# -----------------------------
# Run Both Flask + Bot
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask server on port 8000...")
    Thread(target=run_flask, daemon=True).start()

    print("Starting Wasabi Storage Bot...")
    app.run()
