import os
import time
import math
import boto3
import asyncio
import re
import signal
import atexit
import threading
import socket
import json
import html
import base64
import traceback
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
from botocore.exceptions import NoCredentialsError, ClientError, EndpointConnectionError
from pyrogram.errors import FloodWait
from boto3.s3.transfer import TransferConfig
from botocore.config import Config as BotoConfig
from urllib.parse import quote, urlencode
from flask import Flask, render_template, jsonify

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WASABI_ACCESS_KEY = os.getenv("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.getenv("WASABI_SECRET_KEY")
WASABI_BUCKET = os.getenv("WASABI_BUCKET")
WASABI_REGION = os.getenv("WASABI_REGION")
AUTHORIZED_USERS = [int(user_id) for user_id in os.getenv("AUTHORIZED_USERS", "").split(",") if user_id]
RENDER_URL = os.getenv("RENDER_URL", "").rstrip('/')

# Welcome image URL (you can replace this with your own image)
WELCOME_IMAGE_URL = "https://raw.githubusercontent.com/Mraprguild8133/Telegramstorage-/refs/heads/main/IMG-20250915-WA0013.jpg"

# --- Basic Checks ---
if not all([API_ID, API_HASH, BOT_TOKEN, WASABI_ACCESS_KEY, WASABI_SECRET_KEY, WASABI_BUCKET, WASABI_REGION]):
    print("Missing one or more required environment variables. Please check your .env file.")
    exit()

# --- Initialize Pyrogram Client ---
# Extreme workers for maximum performance
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

# --- Extreme Boto3 Configuration for ULTRA TURBO SPEED ---
# Optimized for maximum parallel processing
boto_config = BotoConfig(
    retries={'max_attempts': 5, 'mode': 'adaptive'},
    max_pool_connections=100,  # Extreme connection pooling
    connect_timeout=30,
    read_timeout=60,
    tcp_keepalive=True,
    s3={'addressing_style': 'virtual'}
)

transfer_config = TransferConfig(
    multipart_threshold=5 * 1024 * 1024,   # Start multipart for files > 5MB
    max_concurrency=50,                    # Extreme parallel threads
    multipart_chunksize=50 * 1024 * 1024,  # Larger chunks for fewer requests
    num_download_attempts=10,              # More retries for stability
    use_threads=True
)

# --- Initialize Boto3 Client for Wasabi with Extreme Settings ---
wasabi_endpoint_url = f'https://s3.{WASABI_REGION}.wasabisys.com'
s3_client = boto3.client(
    's3',
    endpoint_url=wasabi_endpoint_url,
    aws_access_key_id=WASABI_ACCESS_KEY,
    aws_secret_access_key=WASABI_SECRET_KEY,
    config=boto_config  # Apply extreme config
)

# --- Performance Configuration ---
MAX_WORKERS = 10
thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# --- Rate limiting ---
user_limits = {}
MAX_REQUESTS_PER_MINUTE = 30  # Increased limit for power users
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB Ultra size limit
MULTIPART_THRESHOLD = 100 * 1024 * 1024
CHUNK_SIZE = 50 * 1024 * 1024
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# --- Media extensions for player ---
MEDIA_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
}

# --- Flask app for player.html ---
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

# --- Authorization Check ---
async def is_authorized(user_id):
    return not AUTHORIZED_USERS or user_id in AUTHORIZED_USERS

# --- Simple HTTP Server for Health Checks ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "status": "healthy",
                "timestamp": time.time(),
                "bucket": WASABI_BUCKET,
                "performance_mode": "ULTRA_TURBO"
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
        elif self.path == '/stats':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            current_time = time.time()
            active_users = len([k for k, v in user_limits.items() if any(current_time - t < 300 for t in v)])
            
            response = {
                "user_limits_count": len(user_limits),
                "active_users": active_users,
                "performance_mode": "ULTRA_TURBO"
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write("Ultra Turbo Wasabi Storage Bot is running!".encode('utf-8'))

    def log_message(self, format, *args):
        # Disable logging to prevent conflicts with Pyrogram
        return

def run_http_server():
    # Use the PORT environment variable if available (common in cloud platforms)
    port = int(os.environ.get('PORT', 8080))
    
    # Create a simple HTTP server without signal handling
    with HTTPServer(('0.0.0.0', port), HealthHandler) as httpd:
        print(f"HTTP server running on port {port}")
        # Set timeout to prevent blocking
        httpd.timeout = 1
        while True:
            try:
                httpd.handle_request()
            except Exception as e:
                print(f"HTTP server error: {e}")
            time.sleep(5)  # Check for requests every 5 seconds

# --- Wasabi Connection Test & Diagnostics ---
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
        wasabi_endpoint_url = f'https://s3.{WASABI_REGION}.wasabisys.com'
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
            # Test authentication by listing buckets
            s3_client.list_buckets()
            diagnostics["auth_valid"] = True
            
            # Test if bucket exists
            try:
                s3_client.head_bucket(Bucket=WASABI_BUCKET)
                diagnostics["bucket_exists"] = True
                diagnostics["connected"] = True
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    diagnostics["error"] = f"Bucket '{WASABI_BUCKET}' does not exist"
                elif error_code == '403':
                    diagnostics["error"] = f"Access denied to bucket '{WASABI_BUCKET}'"
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

# --- Helper Functions & Classes ---
def humanbytes(size):
    """Converts bytes to a human-readable format."""
    if not size:
        return "0 B"
    power = 1024
    t_n = 0
    power_dict = {0: " B", 1: " KB", 2: " MB", 3: " GB", 4: " TB"}
    while size >= power and t_n < len(power_dict) -1:
        size /= power
        t_n += 1
    return "{:.2f} {}".format(size, power_dict[t_n])

def sanitize_filename(filename):
    """Remove potentially dangerous characters from filenames"""
    # Keep only alphanumeric, spaces, dots, hyphens, and underscores
    filename = re.sub(r'[^a-zA-Z0-9 _.-]', '_', filename)
    # Limit length to avoid issues
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    return filename

def escape_html(text):
    """Escape HTML special characters"""
    if not text:
        return ""
    return html.escape(str(text))

def cleanup():
    """Clean up temporary files on exit"""
    for folder in ['.', './downloads']:
        if os.path.exists(folder):
            for file in os.listdir(folder):
                if file.endswith('.tmp') or file.startswith('pyrogram'):
                    try:
                        os.remove(os.path.join(folder, file))
                    except:
                        pass

atexit.register(cleanup)

async def check_rate_limit(user_id):
    """Check if user has exceeded rate limits"""
    current_time = time.time()
    
    if user_id not in user_limits:
        user_limits[user_id] = []
    
    # Remove requests older than 1 minute
    user_limits[user_id] = [t for t in user_limits[user_id] if current_time - t < 60]
    
    if len(user_limits[user_id]) >= MAX_REQUESTS_PER_MINUTE:
        return False
    
    user_limits[user_id].append(current_time)
    return True

def get_user_folder(user_id):
    """Get user-specific folder path"""
    return f"user_{user_id}"

def create_ultra_progress_bar(percentage, length=12):
    """Create an ultra modern visual progress bar"""
    filled_length = int(length * percentage / 100)
    
    # Create a gradient effect based on progress
    if percentage < 25:
        filled_char = "⚡"
        empty_char = "⚡"
    elif percentage < 50:
        filled_char = "🔥"
        empty_char = "⚡"
    elif percentage < 75:
        filled_char = "🚀"
        empty_char = "🔥"
    else:
        filled_char = "💯"
        empty_char = "🚀"
    
    bar = filled_char * filled_length + empty_char * (length - filled_length)
    return f"{bar}"

async def ultra_progress_reporter(message: Message, status: dict, total_size: int, task: str, start_time: float):
    """Ultra turbo progress reporter with extreme performance metrics"""
    last_update = 0
    speed_samples = []
    
    while status['running']:
        current_time = time.time()
        elapsed_time = current_time - start_time
        
        # Calculate progress
        if total_size > 0:
            percentage = min((status['seen'] / total_size) * 100, 100)
        else:
            percentage = 0
        
        # Calculate speed with smoothing
        speed = status['seen'] / elapsed_time if elapsed_time > 0 else 0
        speed_samples.append(speed)
        if len(speed_samples) > 5:
            speed_samples.pop(0)
        avg_speed = sum(speed_samples) / len(speed_samples) if speed_samples else 0
        
        # Calculate ETA
        remaining = total_size - status['seen']
        eta_seconds = remaining / avg_speed if avg_speed > 0 else 0
        
        # Format ETA
        if eta_seconds > 3600:
            eta = f"{int(eta_seconds/3600)}h {int((eta_seconds%3600)/60)}m"
        elif eta_seconds > 60:
            eta = f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
        else:
            eta = f"{int(eta_seconds)}s" if eta_seconds > 0 else "Calculating..."
        
        # Create the progress bar with ultra design
        progress_bar = create_ultra_progress_bar(percentage)
        
        # Only update if significant change or every 1.5 seconds
        if current_time - last_update > 1.5 or abs(percentage - status.get('last_percentage', 0)) > 2:
            status['last_percentage'] = percentage
            
            # Use HTML formatting
            escaped_task = escape_html(task)
            
            # File name with ellipsis if too long
            display_task = escaped_task
            if len(display_task) > 35:
                display_task = display_task[:32] + "..."
            
            text = (
                f"<b>⚡ ULTRA TURBO MODE</b>\n\n"
                f"<b>📁 {display_task}</b>\n\n"
                f"{progress_bar}\n"
                f"<b>{percentage:.1f}%</b> • {humanbytes(status['seen'])} / {humanbytes(total_size)}\n\n"
                f"<b>🚀 Speed:</b> {humanbytes(avg_speed)}/s\n"
                f"<b>⏱️ ETA:</b> {eta}\n"
                f"<b>🕒 Elapsed:</b> {time.strftime('%M:%S', time.gmtime(elapsed_time))}\n"
                f"<b>🔧 Threads:</b> {transfer_config.max_concurrency}"
            )
            
            try:
                await message.edit_text(text, parse_mode=ParseMode.HTML)
                last_update = current_time
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                # If HTML fails, try without formatting
                try:
                    plain_text = (
                        f"ULTRA TURBO MODE\n\n"
                        f"{display_task}\n\n"
                        f"{progress_bar}\n"
                        f"{percentage:.1f}% • {humanbytes(status['seen'])} / {humanbytes(total_size)}\n\n"
                        f"Speed: {humanbytes(avg_speed)}/s\n"
                        f"ETA: {eta}\n"
                        f"Elapsed: {time.strftime('%M:%S', time.gmtime(elapsed_time))}\n"
                        f"Threads: {transfer_config.max_concurrency}"
                    )
                    await message.edit_text(plain_text)
                    last_update = current_time
                except:
                    pass  # Ignore other edit errors
        
        await asyncio.sleep(0.8)  # Update faster for ultra mode

def ultra_pyrogram_progress_callback(current, total, message, start_time, task):
    """Ultra progress callback for Pyrogram's synchronous operations."""
    try:
        if not hasattr(ultra_pyrogram_progress_callback, 'last_edit_time') or time.time() - ultra_pyrogram_progress_callback.last_edit_time > 1.5:
            percentage = min((current * 100 / total), 100) if total > 0 else 0
            
            # Create an ultra progress bar
            bar_length = 10
            filled = int(bar_length * percentage / 100)
            bar = "🚀" * filled + "⚡" * (bar_length - filled)
            
            # Use HTML formatting
            escaped_task = escape_html(task)
            
            # Truncate long file names
            display_task = escaped_task
            if len(display_task) > 30:
                display_task = display_task[:27] + "..."
            
            elapsed_time = time.time() - start_time
            
            text = (
                f"<b>⬇️ ULTRA DOWNLOAD</b>\n"
                f"<b>📁 {display_task}</b>\n"
                f"{bar} <b>{percentage:.1f}%</b>\n"
                f"<b>⏱️ Elapsed:</b> {time.strftime('%M:%S', time.gmtime(elapsed_time))}"
            )
            
            try:
                message.edit_text(text, parse_mode=ParseMode.HTML)
            except:
                # If HTML fails, try without formatting
                message.edit_text(
                    f"ULTRA DOWNLOAD\n"
                    f"{display_task}\n"
                    f"{bar} {percentage:.1f}%\n"
                    f"Elapsed: {time.strftime('%M:%S', time.gmtime(elapsed_time))}"
                )
            ultra_pyrogram_progress_callback.last_edit_time = time.time()
    except Exception:
        pass

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

def generate_player_links(file_name, presigned_url):
    """Generate player links for various media players with better Android support"""
    # URL encode the presigned URL
    encoded_url = quote(presigned_url, safe='')
    
    # MX Player intent URL (Android deep link format)
    mx_player_url = f"intent://{encoded_url}#Intent;package=com.mxtech.videoplayer.ad;scheme=http;type=video/*;end"
    
    # VLC Player URL (Android deep link format)
    vlc_player_url = f"vlc://{encoded_url}"
    
    # Alternative VLC URL (for different VLC versions)
    vlc_alt_url = f"intent://{encoded_url}#Intent;package=org.videolan.vlc;scheme=http;type=video/*;end"
    
    # Generic streaming URL (for browsers)
    streaming_url = presigned_url
    
    # Direct download URL
    direct_download_url = presigned_url
    
    # Web player URL
    web_player_url = generate_player_url(file_name, presigned_url)
    
    return {
        "mx_player": mx_player_url,
        "vlc_player": vlc_player_url,
        "vlc_alt": vlc_alt_url,
        "streaming": streaming_url,
        "direct_download": direct_download_url,
        "web_player": web_player_url
    }

def create_player_keyboard(file_name, presigned_url):
    """Create inline keyboard with player options optimized for Android"""
    player_links = generate_player_links(file_name, presigned_url)
    
    keyboard = [
        [
            InlineKeyboardButton("🎬 MX Player", url=player_links["mx_player"]),
            InlineKeyboardButton("🔷 VLC Player", url=player_links["vlc_player"])
        ],
        [
            InlineKeyboardButton("🌐 Online Player", url=player_links["streaming"]),
            InlineKeyboardButton("📥 Direct Download", url=player_links["direct_download"])
        ]
    ]
    
    # Add web player if available
    if player_links["web_player"]:
        keyboard.append([InlineKeyboardButton("🖥️ Web Player", url=player_links["web_player"])])
    
    # Add alternative VLC button
    keyboard.append([InlineKeyboardButton("🔄 Alternative VLC", url=player_links["vlc_alt"])])
    
    return InlineKeyboardMarkup(keyboard)

# --- Upload Functions with Error Handling ---
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
                partial(s3_client.upload_file, str(file_path), WASABI_BUCKET, user_file_name)
            )
    except Exception as e:
        # Provide more specific error messages
        if "Access Denied" in str(e):
            raise Exception("Access denied to Wasabi. Check your credentials and bucket permissions.")
        elif "NoSuchBucket" in str(e):
            raise Exception(f"Bucket '{WASABI_BUCKET}' does not exist.")
        elif "Timeout" in str(e):
            raise Exception("Connection to Wasabi timed out. Check your network connection.")
        else:
            raise e

def upload_multipart(file_path, user_file_name, file_size):
    """Multipart upload with error handling"""
    try:
        mpu = s3_client.create_multipart_upload(
            Bucket=WASABI_BUCKET,
            Key=user_file_name
        )
        
        mpu_id = mpu["UploadId"]
        parts = []
        
        try:
            part_count = math.ceil(file_size / CHUNK_SIZE)
            
            futures = []
            with ThreadPoolExecutor(max_workers=min(part_count, MAX_WORKERS)) as executor:
                for part_number in range(1, part_count + 1):
                    start_byte = (part_number - 1) * CHUNK_SIZE
                    end_byte = min(start_byte + CHUNK_SIZE, file_size)
                    
                    future = executor.submit(
                        upload_part,
                        file_path,
                        user_file_name,
                        mpu_id,
                        part_number,
                        start_byte,
                        end_byte
                    )
                    futures.append(future)
                
                for future in as_completed(futures):
                    parts.append(future.result())
            
            parts.sort(key=lambda x: x['PartNumber'])
            
            s3_client.complete_multipart_upload(
                Bucket=WASABI_BUCKET,
                Key=user_file_name,
                UploadId=mpu_id,
                MultipartUpload={'Parts': parts}
            )
            
        except Exception as e:
            s3_client.abort_multipart_upload(
                Bucket=WASABI_BUCKET,
                Key=user_file_name,
                UploadId=mpu_id
            )
            raise e
            
    except Exception as e:
        raise Exception(f"Multipart upload failed: {str(e)}")

def upload_part(file_path, user_file_name, mpu_id, part_number, start_byte, end_byte):
    """Upload a single part with retry logic"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open(file_path, 'rb') as f:
                f.seek(start_byte)
                data = f.read(end_byte - start_byte)
                
                part = s3_client.upload_part(
                    Bucket=WASABI_BUCKET,
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

# --- Bot Handlers ---
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    """Handles the /start command."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
    
    # Test Wasabi connection first
    diagnostics = test_wasabi_connection()
    
    welcome_text = (
        "🚀 <b>ULTRA TURBO CLOUD STORAGE BOT</b>\n\n"
        "Experience extreme speed with our optimized parallel processing technology!\n\n"
        "➡️ <b>To upload:</b> Just send me any file (up to 10GB!)\n"
        "⬅️ <b>To download:</b> Use <code>/download &lt;file_name&gt;</code>\n"
        "🎬 <b>To play:</b> Use <code>/play &lt;file_name&gt;</code>\n"
        "📋 <b>To list files:</b> Use <code>/list</code>\n"
        "📊 <b>To check status:</b> Use <code>/status</code>\n"
        "📱 <b>Player Help:</b> Use <code>/playerhelp</code>\n\n"
        "<b>⚡ Extreme Performance Features:</b>\n"
        "• 50x Multi-threaded parallel processing\n"
        "• 10GB file size support\n"
        "• Adaptive retry system with 10 attempts\n"
        "• Real-time speed monitoring with smoothing\n"
        "• 100 connection pooling for maximum throughput\n"
        "• Memory optimization for large files\n"
        "• TCP Keepalive for stable connections\n\n"
        "<b>💎 Owner:</b> Mraprguild\n"
        "<b>📧 Email:</b> mraprguild@gmail.com\n"
        "<b>📱 Telegram:</b> @Sathishkumar33"
    )
    
    if not diagnostics["connected"]:
        welcome_text += f"\n\n❌ <b>Wasabi Connection Issue:</b> {diagnostics['error']}"
    else:
        welcome_text += "\n\n✅ <b>Wasabi connection is active</b>"
        
    if RENDER_URL:
        welcome_text += "\n\n🎥 <b>Web player support is enabled!</b>"
        
    # Send the welcome image with caption
    await message.reply_photo(
        photo=WELCOME_IMAGE_URL,
        caption=welcome_text,
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command("status"))
async def status_command(client, message: Message):
    """Check Wasabi connection status"""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
    
    diagnostics = test_wasabi_connection()
    
    status_text = "<b>Wasabi Connection Status:</b>\n\n"
    
    if diagnostics["connected"]:
        status_text += "✅ <b>Connected successfully</b>\n"
        status_text += f"• Bucket: {diagnostics.get('bucket_exists', False) and '✅ Exists' or '❌ Missing'}\n"
        status_text += f"• Authentication: {diagnostics.get('auth_valid', False) and '✅ Valid' or '❌ Invalid'}\n"
        status_text += f"• Endpoint: {diagnostics.get('endpoint_reachable', False) and '✅ Reachable' or '❌ Unreachable'}\n"
    else:
        status_text += "❌ <b>Connection failed</b>\n"
        status_text += f"• Error: {diagnostics.get('error', 'Unknown error')}\n"
        status_text += "\n<b>Troubleshooting tips:</b>\n"
        status_text += "1. Check your WASABI_ACCESS_KEY and WASABI_SECRET_KEY\n"
        status_text += "2. Verify the WASABI_BUCKET exists\n"
        status_text += "3. Check your network connection\n"
        status_text += "4. Ensure WASABI_REGION is correct\n"
    
    await message.reply_text(status_text, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("playerhelp"))
async def player_help_command(client, message: Message):
    """Provides instructions for setting up players on Android"""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
        
    help_text = (
        "📱 <b>Android Player Setup Guide</b>\n\n"
        "🎬 <b>MX Player:</b>\n"
        "1. Install MX Player from Play Store\n"
        "2. Make sure 'Open supported links' is enabled in app settings\n"
        "3. When clicking MX Player link, choose 'Open with MX Player'\n\n"
        "🔷 <b>VLC Player:</b>\n"
        "1. Install VLC from Play Store\n"
        "2. Enable 'Play with VLC' in VLC settings → Advanced\n"
        "3. When clicking VLC link, choose 'Open with VLC'\n\n"
        "🌐 <b>Online Player:</b>\n"
        "Works in most mobile browsers without any setup\n\n"
        "📥 <b>Direct Download:</b>\n"
        "Downloads the file to your device for offline viewing\n\n"
        "🖥️ <b>Web Player:</b>\n"
        "Opens a web-based player in your browser"
    )
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("turbo"))
async def turbo_mode_command(client, message: Message):
    """Shows turbo mode status"""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
        
    await message.reply_text(
        f"⚡ <b>ULTRA TURBO MODE ACTIVE</b>\n\n"
        f"<b>Max Concurrency:</b> {transfer_config.max_concurrency} threads\n"
        f"<b>Chunk Size:</b> {humanbytes(transfer_config.multipart_chunksize)}\n"
        f"<b>Multipart Threshold:</b> {humanbytes(transfer_config.multipart_threshold)}\n"
        f"<b>Max File Size:</b> {humanbytes(MAX_FILE_SIZE)}\n"
        f"<b>Connection Pool:</b> {boto_config.max_pool_connections} connections",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    """Handles file uploads to Wasabi using extreme multipart transfers."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
    
    # Check Wasabi connection first
    if s3_client is None:
        await message.reply_text(
            "❌ Wasabi storage is not available. Please check your credentials.\n"
            "Use /status to diagnose the connection issue."
        )
        return
    
    # Check rate limiting
    if not await check_rate_limit(message.from_user.id):
        await message.reply_text("❌ Rate limit exceeded. Please try again in a minute.")
        return

    media = message.document or message.video or message.audio or message.photo
    if not media:
        await message.reply_text("Unsupported file type.")
        return

    # Check file size limit
    if hasattr(media, 'file_size') and media.file_size > MAX_FILE_SIZE:
        await message.reply_text(f"❌ File too large. Maximum size is {humanbytes(MAX_FILE_SIZE)}")
        return

    # Get filename
    if hasattr(media, 'file_name') and media.file_name:
        file_name = media.file_name
    elif message.photo:
        file_name = f"photo_{message.id}.jpg"
    else:
        file_name = "unknown_file"
    
    file_name = sanitize_filename(file_name)
    file_path = None
    status_message = await message.reply_text("⚡ Initializing ULTRA TURBO mode...", quote=True)

    try:
        await status_message.edit_text("⬇️ Downloading from Telegram (Turbo Mode)...")
        file_path = await message.download(
            file_name=DOWNLOAD_DIR / file_name,
            progress=ultra_pyrogram_progress_callback, 
            progress_args=(status_message, time.time(), "Downloading")
        )
        
        user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
        status = {'running': True, 'seen': 0}
        
        def boto_callback(bytes_amount):
            status['seen'] += bytes_amount

        reporter_task = asyncio.create_task(
            ultra_progress_reporter(status_message, status, media.file_size, f"Uploading {file_name} (ULTRA TURBO)", time.time())
        )
        
        await upload_file_to_wasabi(file_path, user_file_name, media.file_size)
        
        status['running'] = False
        await asyncio.sleep(0.1)  # Give the reporter task a moment to finish
        reporter_task.cancel()

        presigned_url = s3_client.generate_presigned_url('get_object', Params={
            'Bucket': WASABI_BUCKET,
            'Key': user_file_name
        }, ExpiresIn=604800)  # 7 days expiration

        keyboard = create_player_keyboard(file_name, presigned_url)
        
        await status_message.edit_text(
            f"✅ <b>Upload Complete!</b>\n\n"
            f"📁 <b>File:</b> <code>{escape_html(file_name)}</code>\n"
            f"📊 <b>Size:</b> {humanbytes(media.file_size)}\n"
            f"🔗 <b>URL:</b> <code>{escape_html(presigned_url[:50])}...</code>\n\n"
            f"🎬 <b>Click below to play/download:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except FloodWait as e:
        await status_message.edit_text(f"⚠️ Flood wait: {e.value} seconds")
        await asyncio.sleep(e.value)
    except Exception as e:
        error_msg = f"❌ Upload failed: {str(e)}"
        if "Access Denied" in str(e):
            error_msg += "\n\nCheck your Wasabi credentials and bucket permissions."
        await status_message.edit_text(error_msg)
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

@app.on_message(filters.command("download"))
async def download_command(client, message: Message):
    """Download a file from Wasabi storage."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
    
    # Check Wasabi connection first
    if s3_client is None:
        await message.reply_text(
            "❌ Wasabi storage is not available. Please check your credentials.\n"
            "Use /status to diagnose the connection issue."
        )
        return
    
    # Check rate limiting
    if not await check_rate_limit(message.from_user.id):
        await message.reply_text("❌ Rate limit exceeded. Please try again in a minute.")
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: /download <file_name>")
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    status_message = await message.reply_text("🔍 Searching for file...", quote=True)

    try:
        # Check if file exists
        s3_client.head_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url('get_object', Params={
            'Bucket': WASABI_BUCKET,
            'Key': user_file_name
        }, ExpiresIn=604800)  # 7 days expiration

        keyboard = create_player_keyboard(file_name, presigned_url)
        
        await status_message.edit_text(
            f"✅ <b>File Found!</b>\n\n"
            f"📁 <b>File:</b> <code>{escape_html(file_name)}</code>\n\n"
            f"🎬 <b>Click below to play/download:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            await status_message.edit_text("❌ File not found.")
        elif error_code == '403':
            await status_message.edit_text("❌ Access denied to file.")
        else:
            await status_message.edit_text(f"❌ Error: {str(e)}")
    except Exception as e:
        await status_message.edit_text(f"❌ Download failed: {str(e)}")

@app.on_message(filters.command("play"))
async def play_command(client, message: Message):
    """Generate a player link for a file."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
    
    # Check Wasabi connection first
    if s3_client is None:
        await message.reply_text(
            "❌ Wasabi storage is not available. Please check your credentials.\n"
            "Use /status to diagnose the connection issue."
        )
        return
    
    # Check rate limiting
    if not await check_rate_limit(message.from_user.id):
        await message.reply_text("❌ Rate limit exceeded. Please try again in a minute.")
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: /play <file_name>")
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    status_message = await message.reply_text("🔍 Searching for file...", quote=True)

    try:
        # Check if file exists
        s3_client.head_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url('get_object', Params={
            'Bucket': WASABI_BUCKET,
            'Key': user_file_name
        }, ExpiresIn=604800)  # 7 days expiration

        keyboard = create_player_keyboard(file_name, presigned_url)
        
        await status_message.edit_text(
            f"🎬 <b>Player Ready!</b>\n\n"
            f"📁 <b>File:</b> <code>{escape_html(file_name)}</code>\n\n"
            f"📱 <b>Click below to play:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            await status_message.edit_text("❌ File not found.")
        elif error_code == '403':
            await status_message.edit_text("❌ Access denied to file.")
        else:
            await status_message.edit_text(f"❌ Error: {str(e)}")
    except Exception as e:
        await status_message.edit_text(f"❌ Player generation failed: {str(e)}")

@app.on_message(filters.command("list"))
async def list_command(client, message: Message):
    """List files in user's folder."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
    
    # Check Wasabi connection first
    if s3_client is None:
        await message.reply_text(
            "❌ Wasabi storage is not available. Please check your credentials.\n"
            "Use /status to diagnose the connection issue."
        )
        return
    
    # Check rate limiting
    if not await check_rate_limit(message.from_user.id):
        await message.reply_text("❌ Rate limit exceeded. Please try again in a minute.")
        return

    user_folder = get_user_folder(message.from_user.id)
    status_message = await message.reply_text("📋 Listing files...", quote=True)

    try:
        response = s3_client.list_objects_v2(
            Bucket=WASABI_BUCKET,
            Prefix=user_folder + "/"
        )
        
        if 'Contents' not in response:
            await status_message.edit_text("📁 No files found in your storage.")
            return
        
        files = response['Contents']
        files.sort(key=lambda x: x['LastModified'], reverse=True)
        
        file_list = []
        total_size = 0
        
        for file in files:
            if file['Key'] == user_folder + "/":
                continue  # Skip the folder itself
                
            file_name = file['Key'].replace(user_folder + "/", "")
            file_size = humanbytes(file['Size'])
            file_date = file['LastModified'].strftime("%Y-%m-%d %H:%M")
            
            file_list.append(f"• {file_name} ({file_size}) - {file_date}")
            total_size += file['Size']
        
        if not file_list:
            await status_message.edit_text("📁 No files found in your storage.")
            return
        
        # Paginate if too many files
        if len(file_list) > 20:
            chunks = [file_list[i:i+20] for i in range(0, len(file_list), 20)]
            for i, chunk in enumerate(chunks):
                list_text = f"📁 <b>Your Files (Page {i+1}/{len(chunks)})</b>\n\n" + "\n".join(chunk[:20])
                list_text += f"\n\n📊 <b>Total:</b> {len(file_list)} files, {humanbytes(total_size)}"
                
                if i == 0:
                    await status_message.edit_text(list_text, parse_mode=ParseMode.HTML)
                else:
                    await message.reply_text(list_text, parse_mode=ParseMode.HTML)
        else:
            list_text = "📁 <b>Your Files</b>\n\n" + "\n".join(file_list)
            list_text += f"\n\n📊 <b>Total:</b> {len(file_list)} files, {humanbytes(total_size)}"
            await status_message.edit_text(list_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        await status_message.edit_text(f"❌ Failed to list files: {str(e)}")

@app.on_message(filters.command("delete"))
async def delete_command(client, message: Message):
    """Delete a file from Wasabi storage."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
    
    # Check Wasabi connection first
    if s3_client is None:
        await message.reply_text(
            "❌ Wasabi storage is not available. Please check your credentials.\n"
            "Use /status to diagnose the connection issue."
        )
        return
    
    # Check rate limiting
    if not await check_rate_limit(message.from_user.id):
        await message.reply_text("❌ Rate limit exceeded. Please try again in a minute.")
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: /delete <file_name>")
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    status_message = await message.reply_text("🗑️ Deleting file...", quote=True)

    try:
        s3_client.delete_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        await status_message.edit_text(f"✅ Deleted: <code>{escape_html(file_name)}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await status_message.edit_text(f"❌ Delete failed: {str(e)}")

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    """Show help information."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
        
    help_text = (
        "🤖 <b>Wasabi Storage Bot Help</b>\n\n"
        "📤 <b>Upload:</b> Send any file (document, video, audio, photo)\n"
        "📥 <b>Download:</b> <code>/download &lt;file_name&gt;</code>\n"
        "🎬 <b>Play:</b> <code>/play &lt;file_name&gt;</code>\n"
        "📋 <b>List files:</b> <code>/list</code>\n"
        "🗑️ <b>Delete:</b> <code>/delete &lt;file_name&gt;</code>\n"
        "📊 <b>Status:</b> <code>/status</code>\n"
        "📱 <b>Player Help:</b> <code>/playerhelp</code>\n"
        "⚡ <b>Turbo Info:</b> <code>/turbo</code>\n\n"
        "🔗 <b>Features:</b>\n"
        "• 10GB file uploads\n"
        "• Multi-threaded parallel transfers\n"
        "• Real-time progress tracking\n"
        "• Android player integration\n"
        "• Web player support\n"
        "• Rate limiting protection\n\n"
        "💎 <b>Owner:</b> Mraprguild\n"
        "📧 <b>Email:</b> mraprguild@gmail.com"
    )
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

# --- Error Handler ---
@app.on_message()
async def error_handler(client, message: Message):
    """Handle unsupported messages."""
    # Check authorization
    if not await is_authorized(message.from_user.id):
        await message.reply_text("❌ Unauthorized access.")
        return
        
    await message.reply_text(
        "❌ Unsupported message type.\n"
        "Send a file to upload or use /help for commands."
    )

# --- Main Function ---
async def main():
    """Main function to run the bot."""
    print("🚀 Starting ULTRA TURBO Wasabi Storage Bot...")
    
    # Test Wasabi connection at startup
    print("🔗 Testing Wasabi connection...")
    diagnostics = test_wasabi_connection()
    
    if not diagnostics["connected"]:
        print(f"❌ Wasabi connection failed: {diagnostics.get('error', 'Unknown error')}")
        print("⚠️  The bot will start but uploads/downloads may fail")
    else:
        print("✅ Wasabi connection successful!")
    
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Start Flask server in a separate thread if RENDER_URL is set
    if RENDER_URL:
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(f"🌐 Flask player server started on port 8000")
    
    print("🤖 Bot is now running. Press Ctrl+C to stop.")
    
    # Start the Pyrogram client
    await app.start()
    
    # Get bot info
    me = await app.get_me()
    print(f"✅ Bot @{me.username} is now online!")
    
    # Keep the bot running
    await asyncio.Event().wait()

# --- Entry Point ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        traceback.print_exc()
    finally:
        # Cleanup
        cleanup()
        print("🧹 Cleanup completed")