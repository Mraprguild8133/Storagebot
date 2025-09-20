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

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
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
# Performance Configuration
# -----------------------------
MAX_WORKERS = 20  # Increased from 10 for better concurrency
thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

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
# Wasabi Connection Test & Diagnostics
# -----------------------------
def test_wasabi_connection():
    """Test connection to Wasabi and return diagnostic information"""
    diagnostics = {
        "connected": False,
        "error": None,
        "bucket_exists": False,
        "endpoint_reachable": False,
        "auth_valid": False
    }
    
    try:
        # Test network connectivity to Wasabi endpoint
        wasabi_endpoint_url = f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com'
        endpoint_hostname = wasabi_endpoint_url.replace('https://', '')
        
        # Test DNS resolution
        try:
            socket.gethostbyname(endpoint_hostname)
            diagnostics["dns_resolved"] = True
        except socket.gaierror:
            diagnostics["error"] = f"DNS resolution failed for {endpoint_hostname}"
            return diagnostics
        
        # Test endpoint reachability
        try:
            response = requests.get(wasabi_endpoint_url, timeout=10)
            diagnostics["endpoint_reachable"] = True
        except requests.exceptions.RequestException as e:
            diagnostics["error"] = f"Endpoint not reachable: {str(e)}"
            return diagnostics
        
        # Test authentication and bucket access
        try:
            s3_config = Config(
                max_pool_connections=100,  # Increased for better performance
                retries={'max_attempts': 3, 'mode': 'standard'},
                connect_timeout=30,
                read_timeout=60,
                s3={
                    'addressing_style': 'virtual',
                    'use_accelerate_endpoint': False,  # Disable for Wasabi
                    'payload_signing_enabled': False,  # Disable for performance
                },
            )
            
            s3_client = boto3.client(
                's3',
                endpoint_url=wasabi_endpoint_url,
                aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
                aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"],
                config=s3_config
            )
            
            # Test authentication by listing buckets
            s3_client.list_buckets()
            diagnostics["auth_valid"] = True
            
            # Test if bucket exists
            try:
                s3_client.head_bucket(Bucket=required_env_vars["WASABI_BUCKET"])
                diagnostics["bucket_exists"] = True
                diagnostics["connected"] = True
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    diagnostics["error"] = f"Bucket '{required_env_vars['WASABI_BUCKET']}' does not exist"
                elif error_code == '403':
                    diagnostics["error"] = f"Access denied to bucket '{required_env_vars['WASABI_BUCKET']}'"
                else:
                    diagnostics["error"] = f"Bucket error: {str(e)}"
                    
        except NoCredentialsError:
            diagnostics["error"] = "Wasabi credentials are missing or invalid"
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidAccessKeyId':
                diagnostics["error"] = "Wasabi access key is invalid"
            elif error_code == 'SignatureDoesNotMatch':
                diagnostics["error"] = "Wasabi secret key is invalid"
            else:
                diagnostics["error"] = f"Authentication error: {str(e)}"
        except EndpointConnectionError:
            diagnostics["error"] = f"Could not connect to Wasabi endpoint: {wasabi_endpoint_url}"
        except Exception as e:
            diagnostics["error"] = f"Unexpected error: {str(e)}"
            
    except Exception as e:
        diagnostics["error"] = f"Connection test failed: {str(e)}"
    
    return diagnostics

# -----------------------------
# Initialize Wasabi S3 client with error handling
# -----------------------------
def create_s3_client():
    """Create S3 client with proper error handling"""
    wasabi_endpoint_url = f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com'
    
    try:
        s3_config = Config(
            max_pool_connections=100,  # Increased for better performance
            retries={'max_attempts': 3, 'mode': 'standard'},
            connect_timeout=30,
            read_timeout=60,
            s3={
                'addressing_style': 'virtual',
                'use_accelerate_endpoint': False,  # Disable for Wasabi
                'payload_signing_enabled': False,  # Disable for performance
            },
        )

        s3_client = boto3.client(
            's3',
            endpoint_url=wasabi_endpoint_url,
            aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
            aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"],
            config=s3_config
        )
        
        # Test connection immediately
        s3_client.list_buckets()
        return s3_client, None
        
    except Exception as e:
        return None, str(e)

# Initialize S3 client
s3_client, s3_error = create_s3_client()
if s3_client is None:
    print(f"Failed to initialize Wasabi client: {s3_error}")
    print("Running connection diagnostics...")
    diagnostics = test_wasabi_connection()
    print(f"Connection diagnostics: {diagnostics}")

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
            encoded_url += '=' * padding
        media_url = base64.urlsafe_b64decode(encoded_url).decode()
        return render_template("player.html", media_type=media_type, media_url=media_url)
    except Exception as e:
        return f"Error decoding URL: {str(e)}", 400

@flask_app.route("/about")
def about():
    return render_template("about.html")

@flask_app.route("/diagnostics")
def diagnostics():
    """Endpoint to check Wasabi connection status"""
    diag = test_wasabi_connection()
    return jsonify(diag)

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)
    
# -----------------------------
# Constants & Helpers
# -----------------------------
MAX_FILE_SIZE = 2000 * 1024 * 1024
MULTIPART_THRESHOLD = 100 * 1024 * 1024
CHUNK_SIZE = 100 * 1024 * 1024  # Increased from 50MB for better performance
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

# -----------------------------
# Upload Functions with Error Handling
# -----------------------------
async def upload_file_to_wasabi(file_path, user_file_name, file_size):
    """Upload file to Wasabi with comprehensive error handling"""
    if s3_client is None:
        raise Exception("Wasabi client not initialized. Check your credentials and connection.")
    
    try:
        if file_size > MULTIPART_THRESHOLD:
            return await asyncio.get_event_loop().run_in_executor(
                thread_pool, 
                partial(upload_multipart, file_path, user_file_name, file_size)
            )
        else:
            return await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                partial(s3_client.upload_file, str(file_path), required_env_vars["WASABI_BUCKET"], user_file_name)
            )
    except Exception as e:
        # Provide more specific error messages
        if "Access Denied" in str(e):
            raise Exception("Access denied to Wasabi. Check your credentials and bucket permissions.")
        elif "NoSuchBucket" in str(e):
            raise Exception(f"Bucket '{required_env_vars['WASABI_BUCKET']}' does not exist.")
        elif "Timeout" in str(e):
            raise Exception("Connection to Wasabi timed out. Check your network connection.")
        else:
            raise e

def upload_multipart(file_path, user_file_name, file_size):
    """Optimized multipart upload with concurrent part uploads"""
    try:
        mpu = s3_client.create_multipart_upload(
            Bucket=required_env_vars["WASABI_BUCKET"],
            Key=user_file_name
        )
        
        mpu_id = mpu["UploadId"]
        parts = []
        
        # Calculate optimal part size (minimum 5MB, maximum 5GB)
        part_size = max(5 * 1024 * 1024, min(CHUNK_SIZE, file_size // 10000))
        part_count = math.ceil(file_size / part_size)
        
        # Use ThreadPoolExecutor for concurrent part uploads
        with ThreadPoolExecutor(max_workers=min(part_count, MAX_WORKERS)) as executor:
            future_to_part = {}
            
            for part_number in range(1, part_count + 1):
                start_byte = (part_number - 1) * part_size
                end_byte = min(start_byte + part_size, file_size)
                
                future = executor.submit(
                    upload_part_optimized,
                    file_path,
                    user_file_name,
                    mpu_id,
                    part_number,
                    start_byte,
                    end_byte
                )
                future_to_part[future] = part_number
            
            # Process completed parts as they finish
            for future in as_completed(future_to_part):
                try:
                    part = future.result()
                    parts.append(part)
                except Exception as e:
                    # Cancel all other uploads if one fails
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
            s3_client.abort_multipart_upload(
                Bucket=required_env_vars["WASABI_BUCKET"],
                Key=user_file_name,
                UploadId=mpu_id
            )
        raise Exception(f"Multipart upload failed: {str(e)}")

def upload_part_optimized(file_path, user_file_name, mpu_id, part_number, start_byte, end_byte):
    """Upload a single part with retry logic and memory optimization"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Use memory-mapped file for efficient reading
            with open(file_path, 'rb') as f:
                f.seek(start_byte)
                # Read in chunks to avoid memory issues
                chunk_size = 8 * 1024 * 1024  # 8MB chunks
                data_parts = []
                bytes_remaining = end_byte - start_byte
                
                while bytes_remaining > 0:
                    read_size = min(chunk_size, bytes_remaining)
                    data_parts.append(f.read(read_size))
                    bytes_remaining -= read_size
                
                # Combine all chunks
                data = b''.join(data_parts)
                
                part = s3_client.upload_part(
                    Bucket=required_env_vars["WASABI_BUCKET"],
                    Key=user_file_name,
                    PartNumber=part_number,
                    UploadId=mpu_id,
                    Body=data
                )
                return {'PartNumber': part_number, 'ETag': part['ETag']}
                
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(2 ** attempt)  # Exponential backoff

# -----------------------------
# Telegram Bot Handlers with Connection Checking
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    # Test Wasabi connection first
    diagnostics = test_wasabi_connection()
    
    welcome_text = (
        "🚀 **Cloud Storage Bot**\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename> to download files\n"
        "Use /list to see your files\n"
        "Use /play <filename> to get a web player link (for media files)\n"
        "Use /status to check Wasabi connection status\n\n"
        "⚠️ Maximum file size: 2GB"
    )
    
    if not diagnostics["connected"]:
        welcome_text += f"\n\n❌ **Wasabi Connection Issue:** {diagnostics['error']}"
    else:
        welcome_text += "\n\n✅ **Wasabi connection is active**"
        
    if required_env_vars["RENDER_URL"]:
        welcome_text += "\n\n🎥 Web player support is enabled!"
        
    await message.reply_text(welcome_text)

@app.on_message(filters.command("status"))
async def status_command(client, message: Message):
    """Check Wasabi connection status"""
    diagnostics = test_wasabi_connection()
    
    status_text = "**Wasabi Connection Status:**\n\n"
    
    if diagnostics["connected"]:
        status_text += "✅ **Connected successfully**\n"
        status_text += f"• Bucket: {diagnostics.get('bucket_exists', False) and '✅ Exists' or '❌ Missing'}\n"
        status_text += f"• Authentication: {diagnostics.get('auth_valid', False) and '✅ Valid' or '❌ Invalid'}\n"
        status_text += f"• Endpoint: {diagnostics.get('endpoint_reachable', False) and '✅ Reachable' or '❌ Unreachable'}\n"
    else:
        status_text += "❌ **Connection failed**\n"
        status_text += f"• Error: {diagnostics.get('error', 'Unknown error')}\n"
        status_text += "\n**Troubleshooting tips:**\n"
        status_text += "1. Check your WASABI_ACCESS_KEY and WASABI_SECRET_KEY\n"
        status_text += "2. Verify the WASABI_BUCKET exists\n"
        status_text += "3. Check your network connection\n"
        status_text += "4. Ensure WASABI_REGION is correct\n"
    
    await message.reply_text(status_text)

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    # Check Wasabi connection first
    if s3_client is None:
        await message.reply_text(
            "❌ Wasabi storage is not available. Please check your credentials.\n"
            "Use /status to diagnose the connection issue."
        )
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

    status_message = await message.reply_text("Downloading file...")

    try:
        # Use in-memory download for smaller files
        if size and size < 10 * 1024 * 1024:  # 10MB threshold
            file_path = await message.download(in_memory=True)
            file_path = DOWNLOAD_DIR / file_name
            with open(file_path, 'wb') as f:
                f.write(file_path.getvalue())
        else:
            file_path = await message.download(file_name=DOWNLOAD_DIR / file_name)
            
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"

        await status_message.edit_text("Uploading to Wasabi storage...")
        
        await upload_file_to_wasabi(file_path, user_file_name, size)

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

        response_text = (
            f"✅ Upload complete!\n\n"
            f"File: {file_name}\n"
            f"Size: {humanbytes(size) if size else 'N/A'}\n"
            f"Direct Link: {presigned_url}"
        )

        if player_url:
            response_text += f"\n\nPlayer URL: {player_url}"

        await status_message.edit_text(response_text)

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        if "Access Denied" in str(e):
            error_msg += "\n\nCheck your Wasabi credentials and bucket permissions."
        elif "NoSuchBucket" in str(e):
            error_msg += f"\n\nBucket '{required_env_vars['WASABI_BUCKET']}' does not exist."
        elif "Timeout" in str(e):
            error_msg += "\n\nNetwork connection timed out. Please try again."
            
        print("Error:", traceback.format_exc())
        await status_message.edit_text(error_msg)
    finally:
        try:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file: {e}")

# -----------------------------
# Additional Bot Commands with Error Handling
# -----------------------------
@app.on_message(filters.command("list"))
async def list_files(client, message: Message):
    if s3_client is None:
        await message.reply_text("Wasabi storage is not available. Use /status to check connection.")
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
        await message.reply_text(f"Your files:\n\n{files_list}")
        
    except Exception as e:
        await message.reply_text(f"Error listing files: {str(e)}")

@app.on_message(filters.command("download"))
async def download_file(client, message: Message):
    if s3_client is None:
        await message.reply_text("Wasabi storage is not available. Use /status to check connection.")
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
            await message.reply_text("File not found.")
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
        
        await message.reply_text(
            f"Download link for {filename}:\n\n{presigned_url}\n\n"
            "This link will expire in 1 hour."
        )
        
    except Exception as e:
        await message.reply_text(f"Error generating download link: {str(e)}")

@app.on_message(filters.command("play"))
async def play_file(client, message: Message):
    if s3_client is None:
        await message.reply_text("Wasabi storage is not available. Use /status to check connection.")
        return
        
    try:
        if len(message.command) < 2:
            await message.reply_text("Please specify a filename. Usage: /play filename")
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
            await message.reply_text("File not found.")
            return
        
        # Generate a presigned URL
        presigned_url = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            partial(
                s3_client.generate_presigned_url,
                'get_object',
                Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file_name},
                ExpiresIn=86400
            )
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
    print("Testing Wasabi connection...")
    diagnostics = test_wasabi_connection()
    print(f"Connection diagnostics: {diagnostics}")
    
    if not diagnostics["connected"]:
        print(f"❌ Wasabi connection failed: {diagnostics['error']}")
        print("Please check your environment variables and try again.")
    else:
        print("✅ Wasabi connection successful!")
    
    print("Starting Flask server on port 8000...")
    Thread(target=run_flask, daemon=True).start()

    print("Starting Wasabi Storage Bot...")
    app.run()
