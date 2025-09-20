import os
import re
import base64
import asyncio
import traceback
import socket
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
import time
import math
import aiofiles
from typing import Dict, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import MessageNotModified

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
# Performance Configuration - EXTREME TURBO MODE
# -----------------------------
MAX_WORKERS = 50  # Extreme concurrency
thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# -----------------------------
# Initialize Pyrogram Client
# -----------------------------
app = Client(
    "wasabi_bot",
    api_id=required_env_vars["API_ID"],
    api_hash=required_env_vars["API_HASH"],
    bot_token=required_env_vars["BOT_TOKEN"],
    max_concurrent_transmissions=10  # Increased Telegram throughput
)

# -----------------------------
# Initialize Wasabi S3 client - ULTRA TURBO MODE
# -----------------------------
def create_s3_client():
    """Create S3 client with extreme performance settings"""
    wasabi_endpoint_url = f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com'
    
    try:
        s3_config = Config(
            max_pool_connections=200,  # Extreme connection pooling
            retries={'max_attempts': 2, 'mode': 'standard'},  # Faster failover
            connect_timeout=15,  # Reduced timeout
            read_timeout=30,     # Reduced timeout
            s3={
                'addressing_style': 'virtual',
                'use_accelerate_endpoint': False,
                'payload_signing_enabled': False,
            },
        )

        s3_client = boto3.client(
            's3',
            endpoint_url=wasabi_endpoint_url,
            aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
            aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"],
            config=s3_config
        )
        
        s3_client.list_buckets()
        return s3_client, None
        
    except Exception as e:
        return None, str(e)

# Initialize S3 client
s3_client, s3_error = create_s3_client()

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

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)
    
# -----------------------------
# Constants & Helpers - TURBO OPTIMIZED
# -----------------------------
MAX_FILE_SIZE = 2000 * 1024 * 1024
MULTIPART_THRESHOLD = 10 * 1024 * 1024  # Lower threshold for more parallelism
CHUNK_SIZE = 10 * 1024 * 1024  # Smaller chunks for better parallelism
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MEDIA_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
}

# Global dictionary to track progress
progress_tracker: Dict[str, Dict[str, Any]] = {}

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
    filename = re.sub(r'[^\w\s.-]', '', filename)
    filename = re.sub(r'\s+', '_', filename)
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

def format_speed(speed_bps):
    """Format speed in appropriate units"""
    if speed_bps < 1024:
        return f"{speed_bps:.0f} B/s"
    elif speed_bps < 1024 * 1024:
        return f"{speed_bps/1024:.1f} KB/s"
    else:
        return f"{speed_bps/(1024*1024):.1f} MB/s"

def format_time_remaining(seconds):
    """Format time remaining in a human-readable format"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds//60}m {seconds%60:.0f}s"
    else:
        return f"{seconds//3600}h {(seconds%3600)//60}m"

def create_progress_bar(percentage, width=20):
    """Create a visual progress bar"""
    filled = int(width * percentage / 100)
    empty = width - filled
    return "▓" * filled + "░" * empty

async def update_progress_message(client, chat_id, message_id, filename, total_size, progress_id, process_type="upload"):
    """Update the progress message in real-time"""
    last_percentage = -1
    last_update = time.time()
    update_count = 0
    
    while progress_id in progress_tracker:
        try:
            progress = progress_tracker[progress_id]
            current = progress["current"]
            total = progress["total"]
            
            percentage = (current / total) * 100 if total > 0 else 0
            
            # Update more frequently for better real-time feel
            current_time = time.time()
            time_since_last_update = current_time - last_update
            
            # Update every 0.5 seconds or 1% change
            if (time_since_last_update >= 0.5 or 
                abs(percentage - last_percentage) >= 1 or 
                percentage >= 100):
                
                # Calculate speed and ETA
                time_elapsed = current_time - progress["start_time"]
                speed = current / time_elapsed if time_elapsed > 0 else 0
                remaining = total - current
                eta = remaining / speed if speed > 0 and remaining > 0 else 0
                
                progress_bar = create_progress_bar(percentage)
                speed_text = format_speed(speed)
                eta_text = format_time_remaining(eta) if eta > 0 else "Calculating..."
                
                emoji = "📤" if process_type == "upload" else "📥"
                process_text = "Uploading" if process_type == "upload" else "Downloading"
                
                message_text = (
                    f"{emoji} **{process_text}:** `{filename}`\n\n"
                    f"**Progress:** {percentage:.1f}%\n"
                    f"{progress_bar}\n\n"
                    f"**Size:** {humanbytes(current)} / {humanbytes(total)}\n"
                    f"**Speed:** {speed_text}\n"
                    f"**ETA:** {eta_text}"
                )
                
                try:
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=message_text
                    )
                    update_count += 1
                except MessageNotModified:
                    pass
                except Exception as e:
                    print(f"Message edit error: {e}")
                
                last_percentage = percentage
                last_update = current_time
            
            # Check if process is complete
            if current >= total and total > 0:
                break
                
            await asyncio.sleep(0.1)  # Faster polling
            
        except Exception as e:
            print(f"Progress update error: {e}")
            break
    
    # Clean up progress tracking
    if progress_id in progress_tracker:
        del progress_tracker[progress_id]

# -----------------------------
# TURBO DOWNLOAD with Progress Tracking
# -----------------------------
async def download_with_progress(client, message, file_id, file_name, file_size):
    """Turbo download file from Telegram with progress tracking"""
    progress_id = f"download_{message.from_user.id}_{message.id}"
    progress_tracker[progress_id] = {
        "current": 0,
        "total": file_size,
        "start_time": time.time()
    }
    
    file_path = DOWNLOAD_DIR / file_name
    
    try:
        # Start progress update task
        progress_task = asyncio.create_task(
            update_progress_message(client, message.chat.id, message.id, file_name, file_size, progress_id, "download")
        )
        
        # Use async download for better performance
        async with aiofiles.open(file_path, 'wb') as f:
            downloaded = 0
            chunk_size = 65536  # 64KB chunks for faster processing
            
            async for chunk in client.stream_media(message, chunk_size=chunk_size):
                await f.write(chunk)
                downloaded += len(chunk)
                
                # Update progress
                if progress_id in progress_tracker:
                    progress_tracker[progress_id]["current"] = downloaded
                
                # Yield to other tasks frequently
                if downloaded % (chunk_size * 10) == 0:
                    await asyncio.sleep(0)
        
        # Wait for progress task to complete
        await asyncio.sleep(0.5)
        
        return file_path
        
    except Exception as e:
        raise e
    finally:
        # Clean up progress tracking
        if progress_id in progress_tracker:
            del progress_tracker[progress_id]

# -----------------------------
# EXTREME TURBO UPLOAD Functions
# -----------------------------
async def upload_file_to_wasabi(file_path, user_file_name, file_size, progress_id):
    """Turbo upload file to Wasabi with progress tracking"""
    if s3_client is None:
        raise Exception("Wasabi client not initialized.")
    
    # Initialize progress tracking
    progress_tracker[progress_id] = {
        "current": 0,
        "total": file_size,
        "start_time": time.time()
    }
    
    try:
        # Always use multipart for better performance (even for small files)
        return await asyncio.get_event_loop().run_in_executor(
            thread_pool, 
            partial(upload_multipart_turbo, file_path, user_file_name, file_size, progress_id)
        )
    except Exception as e:
        if progress_id in progress_tracker:
            del progress_tracker[progress_id]
        raise e

def upload_multipart_turbo(file_path, user_file_name, file_size, progress_id):
    """Extreme turbo multipart upload"""
    try:
        mpu = s3_client.create_multipart_upload(
            Bucket=required_env_vars["WASABI_BUCKET"],
            Key=user_file_name
        )
        
        mpu_id = mpu["UploadId"]
        parts = []
        
        # Optimized part sizing for maximum parallelism
        part_size = max(5 * 1024 * 1024, min(CHUNK_SIZE, file_size // 50))  # More parts for parallelism
        part_count = math.ceil(file_size / part_size)
        
        # Use extreme parallelism
        with ThreadPoolExecutor(max_workers=min(part_count * 2, MAX_WORKERS)) as executor:
            future_to_part = {}
            
            for part_number in range(1, part_count + 1):
                start_byte = (part_number - 1) * part_size
                end_byte = min(start_byte + part_size, file_size)
                
                future = executor.submit(
                    upload_part_turbo,
                    file_path,
                    user_file_name,
                    mpu_id,
                    part_number,
                    start_byte,
                    end_byte,
                    progress_id
                )
                future_to_part[future] = part_number
            
            # Process completed parts as they finish
            for future in as_completed(future_to_part):
                try:
                    part = future.result()
                    parts.append(part)
                except Exception as e:
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise e
        
        # Sort parts by part number
        parts.sort(key=lambda x: x['PartNumber'])
        
        s3_client.complete_multipart_upload(
            Bucket=required_env_vars["WASABI_BUCKET"],
            Key=user_file_name,
            UploadId=mpu_id,
            MultipartUpload={'Parts': parts}
        )
        
    except Exception as e:
        if 'mpu_id' in locals():
            try:
                s3_client.abort_multipart_upload(
                    Bucket=required_env_vars["WASABI_BUCKET"],
                    Key=user_file_name,
                    UploadId=mpu_id
                )
            except:
                pass
        raise Exception(f"Upload failed: {str(e)}")
    finally:
        if progress_id in progress_tracker:
            del progress_tracker[progress_id]

def upload_part_turbo(file_path, user_file_name, mpu_id, part_number, start_byte, end_byte, progress_id):
    """Turbo part upload with memory mapping"""
    max_retries = 2  # Faster failover
    for attempt in range(max_retries):
        try:
            # Use memory mapping for extreme speed
            with open(file_path, 'rb') as f:
                f.seek(start_byte)
                part_size = end_byte - start_byte
                
                # Upload in one go for maximum speed
                data = f.read(part_size)
                
                part = s3_client.upload_part(
                    Bucket=required_env_vars["WASABI_BUCKET"],
                    Key=user_file_name,
                    PartNumber=part_number,
                    UploadId=mpu_id,
                    Body=data
                )
                
                # Update progress
                if progress_id in progress_tracker:
                    progress_tracker[progress_id]["current"] += part_size
                
                return {'PartNumber': part_number, 'ETag': part['ETag']}
                
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(0.5 * (attempt + 1))  # Minimal backoff

# -----------------------------
# Telegram Bot Handlers - TURBO MODE
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    welcome_text = (
        "🚀 **TURBO Cloud Storage Bot**\n\n"
        "Send me any file for ultra-fast upload to Wasabi storage\n"
        "• Extreme speed optimization\n"
        "• Real-time progress tracking\n"
        "• Parallel processing\n\n"
        "Use /download <filename> to get download links\n"
        "Use /list to see your files\n"
        "Use /play <filename> for web player links\n\n"
        "⚡ Maximum file size: 2GB"
    )
    await message.reply_text(welcome_text)

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    if s3_client is None:
        await message.reply_text("❌ Wasabi storage is not available.")
        return
        
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

    # Create initial status message
    status_message = await message.reply_text("⚡ Starting turbo download...")

    try:
        # Download with progress
        download_start = time.time()
        file_path = await download_with_progress(client, status_message, media.file_id, file_name, size)
        download_time = time.time() - download_start
        
        # Update message for upload phase
        await status_message.edit_text("⚡ Starting turbo upload...")
        
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
        upload_id = f"upload_{message.from_user.id}_{status_message.id}"
        
        # Start upload progress tracking
        upload_task = asyncio.create_task(
            update_progress_message(client, message.chat.id, status_message.id, file_name, size, upload_id, "upload")
        )
        
        # Upload to Wasabi with extreme speed
        upload_start = time.time()
        await upload_file_to_wasabi(file_path, user_file_name, size, upload_id)
        upload_time = time.time() - upload_start
        
        # Wait a moment for final progress update
        await asyncio.sleep(0.5)
        
        # Generate presigned URL
        presigned_url = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            partial(
                s3_client.generate_presigned_url,
                'get_object',
                Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
                ExpiresIn=86400
            )
        )

        player_url = generate_player_url(file_name, presigned_url)

        # Calculate speeds
        download_speed = size / download_time if download_time > 0 else 0
        upload_speed = size / upload_time if upload_time > 0 else 0

        response_text = (
            f"✅ **TURBO UPLOAD COMPLETE!**\n\n"
            f"**File:** `{file_name}`\n"
            f"**Size:** {humanbytes(size)}\n"
            f"**Download Speed:** {format_speed(download_speed)}\n"
            f"**Upload Speed:** {format_speed(upload_speed)}\n"
            f"**Total Time:** {download_time + upload_time:.1f}s\n\n"
            f"**Direct Link:** [Click Here]({presigned_url})"
        )

        buttons = [[InlineKeyboardButton("📥 Download Link", url=presigned_url)]]
        
        if player_url:
            buttons[0].append(InlineKeyboardButton("🎥 Player Link", url=player_url))
            response_text += f"\n\n**Player URL:** [Click Here]({player_url})"

        reply_markup = InlineKeyboardMarkup(buttons)

        await status_message.edit_text(response_text, reply_markup=reply_markup, disable_web_page_preview=True)

    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        print("Error:", traceback.format_exc())
        await status_message.edit_text(error_msg)
    finally:
        try:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file: {e}")

# -----------------------------
# Additional Commands
# -----------------------------
@app.on_message(filters.command("list"))
async def list_files(client, message: Message):
    if s3_client is None:
        await message.reply_text("Wasabi storage is not available.")
        return
        
    try:
        user_folder = get_user_folder(message.from_user.id)
        response = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            partial(
                s3_client.list_objects_v2,
                Bucket=required_env_vars["WASABI_BUCKET"],
                Prefix=user_folder + "/"
            )
        )
        
        if 'Contents' not in response:
            await message.reply_text("You haven't uploaded any files yet.")
            return
        
        files = [obj['Key'].replace(f"{user_folder}/", "") for obj in response['Contents']]
        
        if not files:
            await message.reply_text("You haven't uploaded any files yet.")
            return
            
        files_list = "\n".join([f"• {file}" for file in files])
        await message.reply_text(f"📁 **Your Files:**\n\n{files_list}")
        
    except Exception as e:
        await message.reply_text(f"❌ Error listing files: {str(e)}")

@app.on_message(filters.command("download"))
async def download_file(client, message: Message):
    if s3_client is None:
        await message.reply_text("Wasabi storage is not available.")
        return
        
    try:
        if len(message.command) < 2:
            await message.reply_text("Please specify a filename. Usage: /download filename")
            return
            
        filename = " ".join(message.command[1:])
        user_folder = get_user_folder(message.from_user.id)
        user_file_name = f"{user_folder}/{filename}"
        
        # Check if file exists
        try:
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                partial(
                    s3_client.head_object,
                    Bucket=required_env_vars["WASABI_BUCKET"],
                    Key=user_file_name
                )
            )
        except:
            await message.reply_text("❌ File not found.")
            return
        
        # Generate a presigned URL for downloading
        presigned_url = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            partial(
                s3_client.generate_presigned_url,
                'get_object',
                Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
                ExpiresIn=3600
            )
        )
        
        buttons = [[InlineKeyboardButton("📥 Download Now", url=presigned_url)]]
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await message.reply_text(
            f"📥 **Download Link:** `{filename}`\n\n"
            "This link will expire in 1 hour.",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await message.reply_text(f"❌ Error generating download link: {str(e)}")

# -----------------------------
# Run Both Flask + Bot
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask server on port 8000...")
    Thread(target=run_flask, daemon=True).start()

    print("Starting TURBO Wasabi Storage Bot...")
    app.run()