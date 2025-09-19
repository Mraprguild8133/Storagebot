import os
import time
import boto3
import asyncio
import re
import json
import base64
from pathlib import Path
from urllib.parse import quote, urlencode
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration - with validation
required_env_vars = {
    "API_ID": os.getenv("API_ID"),
    "API_HASH": os.getenv("API_HASH"),
    "BOT_TOKEN": os.getenv("BOT_TOKEN"),
    "WASABI_ACCESS_KEY": os.getenv("WASABI_ACCESS_KEY"),
    "WASABI_SECRET_KEY": os.getenv("WASABI_SECRET_KEY"),
    "WASABI_BUCKET": os.getenv("WASABI_BUCKET"),
    "WASABI_REGION": os.getenv("WASABI_REGION"),
    "RENDER_URL": os.getenv("RENDER_URL", "").rstrip('/'),  # Your Render app URL
}

# Check for missing environment variables
missing_vars = [var for var, value in required_env_vars.items() if not value and var != "RENDER_URL"]
if missing_vars:
    raise Exception(f"Missing environment variables: {', '.join(missing_vars)}")

# Initialize clients
app = Client("wasabi_bot", 
             api_id=required_env_vars["API_ID"], 
             api_hash=required_env_vars["API_HASH"], 
             bot_token=required_env_vars["BOT_TOKEN"])

wasabi_endpoint_url = f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com'
s3_client = boto3.client(
    's3',
    endpoint_url=wasabi_endpoint_url,
    aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
    aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"]
)

# Constants
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Supported media extensions for web player
MEDIA_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
}

# Helper functions
def humanbytes(size):
    """Convert bytes to human readable format"""
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

def sanitize_filename(filename):
    """Remove potentially problematic characters from filenames"""
    # Keep only alphanumeric, dots, hyphens, and underscores
    return re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

def get_file_type(filename):
    """Determine file type based on extension"""
    ext = os.path.splitext(filename)[1].lower()
    for file_type, extensions in MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return 'other'

def generate_player_url(filename, presigned_url):
    """Generate web player URL if RENDER_URL is configured"""
    if not required_env_vars["RENDER_URL"]:
        return None
        
    file_type = get_file_type(filename)
    if file_type in ['video', 'audio', 'image']:
        # Create a simple, clean URL without complex query parameters
        # Encode the presigned URL to make it URL-safe
        encoded_url = base64.urlsafe_b64encode(presigned_url.encode()).decode()
        # Remove padding to make it cleaner
        encoded_url = encoded_url.rstrip('=')
        
        # Create a simple URL with just the encoded presigned URL
        return f"{required_env_vars['RENDER_URL']}/player/{file_type}/{encoded_url}"
    return None

def decode_player_url(encoded_url):
    """Decode the encoded URL from the player URL"""
    # Add padding back if needed
    padding = 4 - (len(encoded_url) % 4)
    if padding != 4:
        encoded_url += '=' * padding
    
    try:
        return base64.urlsafe_b64decode(encoded_url).decode()
    except:
        return None

# Bot handlers
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
    # Check file size
    media = message.document or message.video or message.audio or message.photo
    if not media:
        await message.reply_text("Unsupported file type")
        return
        
    if hasattr(media, 'file_size') and media.file_size and media.file_size > MAX_FILE_SIZE:
        await message.reply_text(f"File too large. Maximum size is {humanbytes(MAX_FILE_SIZE)}")
        return

    status_message = await message.reply_text("Downloading file...")
    
    try:
        # Download file
        file_path = await message.download()
        file_name = sanitize_filename(os.path.basename(file_path))
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
        
        # Upload to Wasabi
        await asyncio.to_thread(
            s3_client.upload_file,
            file_path,
            required_env_vars["WASABI_BUCKET"],
            user_file_name
        )
        
        # Generate shareable link
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={
                'Bucket': required_env_vars["WASABI_BUCKET"], 
                'Key': user_file_name
            }, 
            ExpiresIn=86400  # 24 hours
        )
        
        # Check if we can generate a player link
        player_url = generate_player_url(file_name, presigned_url)
        
        # Prepare response
        response_text = (
            f"✅ Upload complete!\n\n"
            f"File: {file_name}\n"
            f"Size: {humanbytes(media.file_size) if hasattr(media, 'file_size') and media.file_size else 'N/A'}\n"
            f"Direct Link: {presigned_url}"
        )
        
        # Add player button if available
        if player_url:
            # Test if the URL is valid for Telegram
            if player_url.startswith(('http://', 'https://')) and len(player_url) <= 256:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎥 Open in Web Player", url=player_url)]
                ])
                await status_message.edit_text(response_text, reply_markup=keyboard)
            else:
                # If URL is invalid for Telegram, just send the text
                response_text += f"\n\nWeb Player: {player_url}"
                await status_message.edit_text(response_text)
        else:
            await status_message.edit_text(response_text)
        
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

@app.on_message(filters.command("download"))
async def download_file_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /download <filename>")
        return

    file_name = " ".join(message.command[1:])
    sanitized_name = sanitize_filename(file_name)
    user_file_name = f"{get_user_folder(message.from_user.id)}/{sanitized_name}"
    local_path = DOWNLOAD_DIR / sanitized_name
    
    status_message = await message.reply_text(f"Downloading {file_name}...")
    
    try:
        # Download from Wasabi
        await asyncio.to_thread(
            s3_client.download_file,
            required_env_vars["WASABI_BUCKET"],
            user_file_name,
            str(local_path)
        )
        
        # Send to user
        await message.reply_document(
            document=str(local_path),
            caption=f"Downloaded: {file_name}"
        )
        
        await status_message.delete()
        
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

@app.on_message(filters.command("play"))
async def play_file_handler(client, message: Message):
    if not required_env_vars["RENDER_URL"]:
        await message.reply_text("Web player is not configured. Please set RENDER_URL environment variable.")
        return
        
    if len(message.command) < 2:
        await message.reply_text("Usage: /play <filename>")
        return

    file_name = " ".join(message.command[1:])
    sanitized_name = sanitize_filename(file_name)
    user_file_name = f"{get_user_folder(message.from_user.id)}/{sanitized_name}"
    
    status_message = await message.reply_text(f"Generating player link for {file_name}...")
    
    try:
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={
                'Bucket': required_env_vars["WASABI_BUCKET"], 
                'Key': user_file_name
            }, 
            ExpiresIn=86400  # 24 hours
        )
        
        # Generate player URL
        player_url = generate_player_url(file_name, presigned_url)
        
        if player_url:
            # Test if the URL is valid for Telegram
            if player_url.startswith(('http://', 'https://')) and len(player_url) <= 256:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎥 Open in Web Player", url=player_url)]
                ])
                await status_message.edit_text(
                    f"Player link for {file_name}:",
                    reply_markup=keyboard
                )
            else:
                # If URL is invalid for Telegram, just send the text
                await status_message.edit_text(
                    f"Player link for {file_name}:\n\n{player_url}"
                )
        else:
            await status_message.edit_text(
                f"File type not supported for web player. Supported formats: "
                f"{', '.join([ext for exts in MEDIA_EXTENSIONS.values() for ext in exts])}"
            )
        
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")

@app.on_message(filters.command("list"))
async def list_files(client, message: Message):
    try:
        user_prefix = get_user_folder(message.from_user.id) + "/"
        response = await asyncio.to_thread(
            s3_client.list_objects_v2, 
            Bucket=required_env_vars["WASABI_BUCKET"], 
            Prefix=user_prefix
        )
        
        if 'Contents' not in response:
            await message.reply_text("No files found")
            return
        
        files = []
        for obj in response['Contents']:
            file_name = obj['Key'].replace(user_prefix, "")
            if file_name:  # Skip empty names (folder itself)
                file_type = get_file_type(file_name)
                file_icon = "🎥" if file_type in ["video", "audio"] else "📄"
                files.append(f"{file_icon} {file_name} ({humanbytes(obj['Size'])})")
        
        files_list = "\n".join(files)
        await message.reply_text(f"Your files:\n\n{files_list}")
    
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")

if __name__ == "__main__":
    print("Starting Wasabi Storage Bot with Web Player support...")
    app.run()
