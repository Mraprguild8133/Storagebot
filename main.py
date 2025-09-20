import os
import time
import boto3
import asyncio
import re
import base64
import aiohttp
import aiofiles
import gzip
import math
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from urllib.parse import quote
import logging

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

# Performance settings
DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for multipart downloads
MAX_WORKERS = 10  # Maximum parallel downloads
COMPRESSION_THRESHOLD = 5 * 1024 * 1024  # Compress files larger than 5MB

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

# Configure Wasabi S3 client with optimized settings
try:
    wasabi_endpoint_url = f'https://s3.{WASABI_REGION}.wasabisys.com'
    
    # Wasabi requires special configuration with optimized settings
    session = boto3.Session()
    s3_client = session.client(
        's3',
        endpoint_url=wasabi_endpoint_url,
        aws_access_key_id=WASABI_ACCESS_KEY,
        aws_secret_access_key=WASABI_SECRET_KEY,
        region_name=WASABI_REGION,
        config=boto3.session.Config(
            max_pool_connections=MAX_WORKERS * 2,
            retries={'max_attempts': 3, 'mode': 'standard'},
            s3={'addressing_style': 'virtual'},
            signature_version='s3v4'
        )
    )
    
    # Test connection
    s3_client.head_bucket(Bucket=WASABI_BUCKET)
    logger.info("Successfully connected to Wasabi bucket")
    
except Exception as e:
    logger.error(f"Wasabi connection failed: {e}")
    # Try alternative endpoint format (some regions use different formats)
    try:
        wasabi_endpoint_url = f'https://{WASABI_BUCKET}.s3.{WASABI_REGION}.wasabisys.com'
        s3_client = boto3.client(
            's3',
            endpoint_url=wasabi_endpoint_url,
            aws_access_key_id=WASABI_ACCESS_KEY,
            aws_secret_access_key=WASABI_SECRET_KEY,
            region_name=WASABI_REGION,
            config=boto3.session.Config(max_pool_connections=MAX_WORKERS * 2)
        )
        s3_client.head_bucket(Bucket=WASABI_BUCKET)
        logger.info("Successfully connected to Wasabi bucket with alternative endpoint")
    except Exception as alt_e:
        logger.error(f"Alternative connection also failed: {alt_e}")
        raise Exception(f"Could not connect to Wasabi: {alt_e}")

# Create a thread pool for parallel operations
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

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
        # Add padding if needed for base64 decoding
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
# Media Type Detection
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

def sanitize_filename(filename):
    """Remove potentially dangerous characters from filenames"""
    filename = re.sub(r'[^a-zA-Z0-9 _.-]', '_', filename)
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    return filename

def get_user_folder(user_id):
    return f"user_{user_id}"

def create_download_keyboard(presigned_url, player_url=None):
    """Create inline keyboard with download option"""
    keyboard = []
    
    if player_url:
        keyboard.append([InlineKeyboardButton("🎬 Web Player", url=player_url)])
    
    keyboard.append([InlineKeyboardButton("📥 Direct Download", url=presigned_url)])
    
    return InlineKeyboardMarkup(keyboard)

# High-speed download functions
async def download_file_part(session, url, start_byte, end_byte, part_number, output_path):
    """Download a specific part of a file"""
    headers = {'Range': f'bytes={start_byte}-{end_byte}'}
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        async with aiofiles.open(f"{output_path}.part{part_number}", 'wb') as f:
            async for chunk in response.content.iter_chunked(256 * 1024):  # 256KB chunks
                await f.write(chunk)
    return part_number

async def download_with_progress(session, url, file_path, file_size, status_message, file_name):
    """Download file with progress tracking using multiple connections"""
    start_time = time.time()
    last_update_time = start_time
    downloaded_size = 0
    
    # For small files, use single connection
    if file_size < DOWNLOAD_CHUNK_SIZE * 2:
        async with session.get(url) as response:
            response.raise_for_status()
            async with aiofiles.open(file_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(256 * 1024):  # 256KB chunks
                    await f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    # Update progress every 1 second
                    current_time = time.time()
                    if current_time - last_update_time >= 1:
                        elapsed = current_time - start_time
                        speed = downloaded_size / elapsed
                        eta = (file_size - downloaded_size) / speed if speed > 0 else 0
                        
                        progress = (downloaded_size / file_size) * 100
                        progress_bar = "[" + "=" * int(progress / 5) + ">" + " " * (20 - int(progress / 5)) + "]"
                        
                        await status_message.edit_text(
                            f"📥 Downloading: {file_name}\n"
                            f"{progress_bar} {progress:.1f}%\n"
                            f"📦 {humanbytes(downloaded_size)} / {humanbytes(file_size)}\n"
                            f"⚡ {humanbytes(speed)}/s\n"
                            f"⏱️ ETA: {eta:.1f}s"
                        )
                        last_update_time = current_time
        return
    
    # For large files, use multipart download
    part_size = DOWNLOAD_CHUNK_SIZE
    num_parts = math.ceil(file_size / part_size)
    
    # Create download tasks for each part
    tasks = []
    for i in range(num_parts):
        start_byte = i * part_size
        end_byte = min(start_byte + part_size - 1, file_size - 1)
        tasks.append(download_file_part(session, url, start_byte, end_byte, i, file_path))
    
    # Execute downloads in parallel
    completed = 0
    for coro in asyncio.as_completed(tasks):
        part_number = await coro
        completed += 1
        downloaded_size = completed * part_size
        
        # Update progress every 1 second
        current_time = time.time()
        if current_time - last_update_time >= 1:
            elapsed = current_time - start_time
            speed = downloaded_size / elapsed
            eta = (file_size - downloaded_size) / speed if speed > 0 else 0
            
            progress = (downloaded_size / file_size) * 100
            progress_bar = "[" + "=" * int(progress / 5) + ">" + " " * (20 - int(progress / 5)) + "]"
            
            await status_message.edit_text(
                f"📥 Downloading: {file_name}\n"
                f"{progress_bar} {progress:.1f}%\n"
                f"📦 {humanbytes(downloaded_size)} / {humanbytes(file_size)}\n"
                f"⚡ {humanbytes(speed)}/s\n"
                f"⏱️ ETA: {eta:.1f}s\n"
                f"🔗 Parts: {completed}/{num_parts}"
            )
            last_update_time = current_time
    
    # Combine parts into single file
    async with aiofiles.open(file_path, 'wb') as output_file:
        for i in range(num_parts):
            part_path = f"{file_path}.part{i}"
            async with aiofiles.open(part_path, 'rb') as part_file:
                content = await part_file.read()
                await output_file.write(content)
            os.remove(part_path)

async def compress_file(input_path, output_path):
    """Compress file using gzip"""
    async with aiofiles.open(input_path, 'rb') as f_in:
        async with aiofiles.open(output_path, 'wb') as f_out:
            async with gzip.GzipFile(fileobj=f_out, mode='wb') as gz:
                while True:
                    chunk = await f_in.read(256 * 1024)  # 256KB chunks
                    if not chunk:
                        break
                    gz.write(chunk)
    return output_path

# Bot handlers
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
    
    try:
        # Download file
        file_path = await message.download()
        file_name = sanitize_filename(os.path.basename(file_path))
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
        
        # Upload to Wasabi
        await asyncio.to_thread(
            s3_client.upload_file,
            file_path,
            WASABI_BUCKET,
            user_file_name
        )
        
        # Generate shareable link
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={'Bucket': WASABI_BUCKET, 'Key': user_file_name}, 
            ExpiresIn=86400
        )
        
        # Generate player URL if supported
        player_url = generate_player_url(file_name, presigned_url)
        
        # Create keyboard with options
        keyboard = create_download_keyboard(presigned_url, player_url)
        
        file_size = media.file_size if hasattr(media, 'file_size') else 0
        if message.photo:
            file_size = os.path.getsize(file_path)
        
        response_text = f"✅ Upload complete!\n\n📁 File: {file_name}\n📦 Size: {humanbytes(file_size)}\n⏰ Link expires: 24 hours"
        
        if player_url:
            response_text += f"\n\n🎬 Web Player: {player_url}"
        
        await status_message.edit_text(
            response_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
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
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    local_path = f"./downloads/{file_name}"
    os.makedirs("./downloads", exist_ok=True)
    
    status_message = await message.reply_text(f"Generating download link for {file_name}...")
    
    try:
        # Get file info
        file_info = s3_client.head_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        file_size = file_info['ContentLength']
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={'Bucket': WASABI_BUCKET, 'Key': user_file_name}, 
            ExpiresIn=3600  # 1 hour for download
        )
        
        # Download with high-speed method
        await status_message.edit_text(f"🚀 Starting high-speed download: {file_name}")
        
        connector = aiohttp.TCPConnector(limit=MAX_WORKERS, force_close=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            await download_with_progress(session, presigned_url, local_path, file_size, status_message, file_name)
        
        # Check if we should compress the file
        final_path = local_path
        if file_size > COMPRESSION_THRESHOLD and not file_name.lower().endswith(('.zip', '.rar', '.7z', '.gz')):
            await status_message.edit_text(f"📦 Compressing {file_name} for faster transfer...")
            compressed_path = f"{local_path}.gz"
            await compress_file(local_path, compressed_path)
            final_path = compressed_path
            os.remove(local_path)
        
        # Send to user
        caption = f"Downloaded: {file_name}"
        if final_path.endswith('.gz'):
            caption += " (compressed)"
        
        await message.reply_document(
            document=final_path,
            caption=caption
        )
        
        await status_message.delete()
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        for path in [local_path, f"{local_path}.gz"]:
            if os.path.exists(path):
                os.remove(path)

# -----------------------------
# Player Command Handler
# -----------------------------
@app.on_message(filters.command("play"))
async def play_file(client, message: Message):
    try:
        if len(message.command) < 2:
            await message.reply_text("Please specify a filename. Usage: /play filename")
            return
            
        filename = " ".join(message.command[1:])
        user_folder = get_user_folder(message.from_user.id)
        user_file_name = f"{user_folder}/{filename}"
        
        # Generate a presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': WASABI_BUCKET, 'Key': user_file_name},
            ExpiresIn=86400
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
        await message.reply_text(f"File not found or error generating player link: {str(e)}")

@app.on_message(filters.command("list"))
async def list_files(client, message: Message):
    try:
        user_prefix = get_user_folder(message.from_user.id) + "/"
        response = s3_client.list_objects_v2(
            Bucket=WASABI_BUCKET, 
            Prefix=user_prefix
        )
        
        if 'Contents' not in response:
            await message.reply_text("No files found")
            return
        
        files = [obj['Key'].replace(user_prefix, "") for obj in response['Contents']]
        files_list = "\n".join([f"• {file}" for file in files[:15]])  # Show first 15 files
        
        if len(files) > 15:
            files_list += f"\n\n...and {len(files) - 15} more files"
        
        await message.reply_text(f"📁 Your files:\n\n{files_list}")
    
    except Exception as e:
        logger.error(f"List files error: {e}")
        await message.reply_text(f"Error: {str(e)}")

@app.on_message(filters.command("delete"))
async def delete_file(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /delete <filename>")
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    
    try:
        # Delete file from Wasabi
        s3_client.delete_object(
            Bucket=WASABI_BUCKET,
            Key=user_file_name
        )
        
        await message.reply_text(f"✅ Deleted: {file_name}")
    
    except Exception as e:
        logger.error(f"Delete error: {e}")
        await message.reply_text(f"Error: {str(e)}")

# -----------------------------
# Flask Server Startup
# -----------------------------
print("Starting Flask server on port 8000...")
Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    print("Starting Wasabi Storage Bot with High-Speed Downloads...")
    app.run()
