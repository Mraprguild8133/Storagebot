import os
import time
import boto3
import asyncio
import re
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
from dotenv import load_dotenv
from urllib.parse import quote, urlencode, parse_qs
from botocore.exceptions import ClientError

# Load environment variables
load_dotenv()

# Configuration
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WASABI_ACCESS_KEY = os.getenv("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.getenv("WASABI_SECRET_KEY")
WASABI_BUCKET = os.getenv("WASABI_BUCKET")
WASABI_REGION = os.getenv("WASABI_REGION")
RENDER_URL = os.getenv("RENDER_URL", "")  # Your Render app URL
PORT = int(os.environ.get('PORT', 5000))

# Initialize clients
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

wasabi_endpoint_url = f'https://s3.{WASABI_REGION}.wasabisys.com'
s3_client = boto3.client(
    's3',
    endpoint_url=wasabi_endpoint_url,
    aws_access_key_id=WASABI_ACCESS_KEY,
    aws_secret_access_key=WASABI_SECRET_KEY
)

# HTTP Server for Render with Web Player support
class WebPlayerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"status": "healthy", "service": "wasabi-storage-bot"}
            self.wfile.write(json.dumps(response).encode())
        
        elif self.path.startswith('/player/'):
            try:
                # Extract filename from URL
                filename = self.path.split('/player/')[1]
                if '?' in filename:
                    filename = filename.split('?')[0]
                
                # URL decode filename
                from urllib.parse import unquote
                filename = unquote(filename)
                
                # Generate presigned URL for the file
                presigned_url = s3_client.generate_presigned_url(
                    'get_object', 
                    Params={'Bucket': WASABI_BUCKET, 'Key': filename}, 
                    ExpiresIn=3600  # 1 hour expiration for web player
                )
                
                # Serve the web player HTML
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                player_html = self.create_web_player_html(filename, presigned_url)
                self.wfile.write(player_html.encode())
                
            except Exception as e:
                self.send_response(404)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                error_html = f"""
                <!DOCTYPE html>
                <html>
                <head><title>Error</title></head>
                <body>
                    <h1>File Not Found</h1>
                    <p>Error: {str(e)}</p>
                    <p>The requested file could not be found or accessed.</p>
                </body>
                </html>
                """
                self.wfile.write(error_html.encode())
        
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            welcome_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Wasabi Storage Bot Web Player</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; text-align: center; }
                    .container { max-width: 600px; margin: 0 auto; }
                    h1 { color: #333; }
                    p { color: #666; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚀 Wasabi Storage Bot</h1>
                    <p>This service provides web player functionality for files stored in Wasabi cloud storage.</p>
                    <p>Use the Telegram bot to upload files and generate player links.</p>
                    <p>Player URLs look like: <code>https://your-render-url.herokuapp.com/player/filename.ext</code></p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(welcome_html.encode())
        
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"404 - Page Not Found")

    def create_web_player_html(self, filename, presigned_url):
        """Create HTML web player for the file"""
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Player - {filename}</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{ 
                        margin: 0; 
                        padding: 20px; 
                        background: #1a1a1a; 
                        font-family: Arial, sans-serif; 
                        color: white;
                    }}
                    .container {{ 
                        max-width: 1000px; 
                        margin: 0 auto; 
                        background: #2d2d2d; 
                        padding: 20px; 
                        border-radius: 10px; 
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                    }}
                    h1 {{ 
                        margin-top: 0; 
                        color: #fff;
                        text-align: center;
                        font-size: 1.5em;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
                    }}
                    video {{ 
                        width: 100%; 
                        border-radius: 8px;
                        background: #000;
                    }}
                    .controls {{
                        margin-top: 20px;
                        text-align: center;
                    }}
                    .download-btn {{ 
                        display: inline-block; 
                        padding: 12px 24px; 
                        background: #007bff; 
                        color: white; 
                        text-decoration: none; 
                        border-radius: 6px;
                        font-weight: bold;
                        transition: background 0.3s;
                    }}
                    .download-btn:hover {{
                        background: #0056b3;
                    }}
                    .info {{
                        margin-top: 15px;
                        color: #ccc;
                        text-align: center;
                        font-size: 0.9em;
                    }}
                    @media (max-width: 768px) {{
                        body {{ padding: 10px; }}
                        .container {{ padding: 15px; }}
                        h1 {{ font-size: 1.2em; }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🎬 {filename}</h1>
                    <video controls autoplay playsinline>
                        <source src="{presigned_url}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                    <div class="controls">
                        <a href="{presigned_url}" class="download-btn" download="{filename}">📥 Download File</a>
                    </div>
                    <div class="info">
                        <p>Player hosted on Render • Link expires in 1 hour</p>
                    </div>
                </div>
                <script>
                    // Auto-fullscreen on mobile devices
                    if (/Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {{
                        const video = document.querySelector('video');
                        video.addEventListener('play', function() {{
                            this.requestFullscreen().catch(err => {{
                                console.log('Fullscreen error:', err);
                            }});
                        }});
                    }}
                </script>
            </body>
            </html>
            """
        
        elif file_ext in ['.mp3', '.wav', '.ogg', '.m4a']:
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Player - {filename}</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{ 
                        margin: 0; 
                        padding: 20px; 
                        background: #1a1a1a; 
                        font-family: Arial, sans-serif; 
                        color: white;
                    }}
                    .container {{ 
                        max-width: 600px; 
                        margin: 0 auto; 
                        background: #2d2d2d; 
                        padding: 30px; 
                        border-radius: 10px; 
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                        text-align: center;
                    }}
                    h1 {{ 
                        margin-top: 0; 
                        color: #fff;
                        font-size: 1.5em;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
                    }}
                    audio {{ 
                        width: 100%; 
                        margin: 30px 0;
                    }}
                    .download-btn {{ 
                        display: inline-block; 
                        padding: 12px 24px; 
                        background: #007bff; 
                        color: white; 
                        text-decoration: none; 
                        border-radius: 6px;
                        font-weight: bold;
                        transition: background 0.3s;
                    }}
                    .download-btn:hover {{
                        background: #0056b3;
                    }}
                    .info {{
                        margin-top: 20px;
                        color: #ccc;
                        font-size: 0.9em;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🎵 {filename}</h1>
                    <audio controls autoplay>
                        <source src="{presigned_url}">
                        Your browser does not support the audio element.
                    </audio>
                    <br>
                    <a href="{presigned_url}" class="download-btn" download="{filename}">📥 Download File</a>
                    <div class="info">
                        <p>Player hosted on Render • Link expires in 1 hour</p>
                    </div>
                </div>
            </body>
            </html>
            """
        
        else:
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Download - {filename}</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{ 
                        margin: 0; 
                        padding: 20px; 
                        background: #1a1a1a; 
                        font-family: Arial, sans-serif; 
                        color: white;
                    }}
                    .container {{ 
                        max-width: 600px; 
                        margin: 0 auto; 
                        background: #2d2d2d; 
                        padding: 40px; 
                        border-radius: 10px; 
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                        text-align: center;
                    }}
                    h1 {{ 
                        margin-top: 0; 
                        color: #fff;
                        margin-bottom: 20px;
                    }}
                    .download-btn {{ 
                        display: inline-block; 
                        padding: 15px 30px; 
                        background: #007bff; 
                        color: white; 
                        text-decoration: none; 
                        border-radius: 6px;
                        font-size: 1.2em;
                        font-weight: bold;
                        transition: background 0.3s;
                        margin: 20px 0;
                    }}
                    .download-btn:hover {{
                        background: #0056b3;
                    }}
                    .info {{
                        margin-top: 20px;
                        color: #ccc;
                        font-size: 0.9em;
                    }}
                    .file-icon {{
                        font-size: 4em;
                        margin-bottom: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="file-icon">📄</div>
                    <h1>{filename}</h1>
                    <p>This file type cannot be previewed in the browser.</p>
                    <a href="{presigned_url}" class="download-btn" download="{filename}">📥 Download File</a>
                    <div class="info">
                        <p>Player hosted on Render • Link expires in 1 hour</p>
                    </div>
                </div>
            </body>
            </html>
            """

def run_http_server():
    with HTTPServer(('0.0.0.0', PORT), WebPlayerHandler) as httpd:
        print(f"HTTP server running on port {PORT}")
        print(f"Web player available at: http://0.0.0.0:{PORT}/player/")
        httpd.serve_forever()

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

def list_user_files(user_id):
    """List all files for a specific user"""
    try:
        user_prefix = f"user_{user_id}/"
        response = s3_client.list_objects_v2(
            Bucket=WASABI_BUCKET, 
            Prefix=user_prefix
        )
        
        if 'Contents' not in response:
            return []
        
        files = [obj['Key'].replace(user_prefix, "") for obj in response['Contents']]
        return files
    except Exception as e:
        print(f"Error listing files: {e}")
        return []

def validate_url(url):
    """Validate and clean URL for Telegram buttons"""
    if not url:
        return None
    
    # Remove any unwanted characters and ensure proper URL format
    url = url.strip()
    
    # Check if URL starts with http:// or https://
    if not url.startswith(('http://', 'https://')):
        # Try to fix common issues
        if url.startswith('//'):
            url = 'https:' + url
        elif '://' not in url:
            url = 'https://' + url
    
    # Basic URL validation
    if len(url) > 512:  # Telegram URL length limit
        print(f"URL too long: {len(url)} characters")
        return None
    
    # Check for invalid characters
    invalid_chars = [' ', '<', '>', '"', "'", '`', '{', '}', '[', ']']
    if any(char in url for char in invalid_chars):
        print(f"URL contains invalid characters: {url}")
        return None
    
    return url

def generate_render_player_url(filename):
    """Generate Render web player URL with proper encoding"""
    try:
        # Properly encode the filename for URL
        encoded_filename = quote(filename, safe='')
        
        if RENDER_URL:
            base_url = RENDER_URL.rstrip('/')
            player_url = f"{base_url}/player/{encoded_filename}"
        else:
            player_url = f"http://localhost:{PORT}/player/{encoded_filename}"
        
        return validate_url(player_url)
    except Exception as e:
        print(f"Error generating render player URL: {e}")
        return None

def generate_presigned_url_safe(filename):
    """Generate presigned URL with error handling"""
    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={'Bucket': WASABI_BUCKET, 'Key': filename}, 
            ExpiresIn=86400  # 24 hours
        )
        return validate_url(presigned_url)
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return None

def create_player_keyboard(filename, presigned_url, render_player_url):
    """Create inline keyboard with player options and URL validation"""
    keyboard = []
    
    # Add Web Player button if URL is valid
    if render_player_url:
        keyboard.append([InlineKeyboardButton("🌐 Web Player (Render)", url=render_player_url)])
    
    # Add Direct Download button if URL is valid
    if presigned_url:
        keyboard.append([InlineKeyboardButton("📥 Direct Download", url=presigned_url)])
    
    # If both URLs are invalid, don't show any buttons
    if not keyboard:
        return None
    
    return InlineKeyboardMarkup(keyboard)

# Bot handlers
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    render_url_note = f"\n🌐 Web Player: `{RENDER_URL}`" if RENDER_URL else "\n🌐 Web Player: Configure RENDER_URL in environment"
    
    await message.reply_text(
        f"🚀 *Cloud Storage Bot with Web Player*\n\n"
        f"Send me any file to upload to Wasabi storage\n"
        f"Use `/download filename` to download files\n"
        f"Use `/play filename` to get web player links\n"
        f"Use `/list` to see your files\n"
        f"{render_url_note}\n\n"
        f"📝 *Note:* Filenames are case\-sensitive\!",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    media = message.document or message.video or message.audio or message.photo
    if not media:
        await message.reply_text("Unsupported file type")
        return

    status_message = await message.reply_text("📥 Downloading file\.\.\.", parse_mode=ParseMode.MARKDOWN)
    
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
        
        # Generate shareable links with validation
        presigned_url = generate_presigned_url_safe(user_file_name)
        render_player_url = generate_render_player_url(user_file_name)
        
        # Create keyboard with player options (only if URLs are valid)
        keyboard = create_player_keyboard(file_name, presigned_url, render_player_url)
        
        file_size = media.file_size if hasattr(media, 'file_size') else "Unknown"
        
        message_text = (
            f"✅ *Upload complete\!*\n\n"
            f"📁 *File:* `{file_name}`\n"
            f"📦 *Size:* {humanbytes(file_size)}\n"
            f"⏰ *Direct link expires:* 24 hours\n"
        )
        
        if render_player_url:
            message_text += f"🌐 *Web player:* 1 hour\n\n"
        else:
            message_text += "\n"
            
        message_text += f"💡 Use `/play {file_name}` to access this file later"
        
        await status_message.edit_text(
            message_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard  # This can be None if URLs are invalid
        )
        
    except Exception as e:
        error_msg = str(e)
        # Handle specific Wasabi errors
        if "Access Denied" in error_msg:
            error_msg = "Access denied to Wasabi. Check your credentials and bucket permissions."
        elif "NoSuchBucket" in error_msg:
            error_msg = "Bucket does not exist. Check your WASABI_BUCKET setting."
        
        await status_message.edit_text(f"❌ *Error:* {error_msg}", parse_mode=ParseMode.MARKDOWN)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.on_message(filters.command("play"))
async def play_file_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(
            "Usage: `/play filename`\n\nUse `/list` to see your available files",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    
    status_message = await message.reply_text(f"🔍 Looking for: `{file_name}`\.\.\.", parse_mode=ParseMode.MARKDOWN)
    
    try:
        # Check if file exists
        s3_client.head_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        
        # Generate shareable links with validation
        presigned_url = generate_presigned_url_safe(user_file_name)
        render_player_url = generate_render_player_url(user_file_name)
        
        # Create keyboard with player options (only if URLs are valid)
        keyboard = create_player_keyboard(file_name, presigned_url, render_player_url)
        
        message_text = f"🎬 *Player ready for:* `{file_name}`\n\n"
        
        if render_player_url:
            message_text += f"⏰ *Link expires:* 1 hour\n"
            message_text += f"🌐 *Web Player hosted on Render*"
        elif presigned_url:
            message_text += f"⏰ *Direct link expires:* 24 hours\n"
            message_text += f"🔗 *Direct download only*"
        else:
            message_text += f"❌ *Could not generate valid links*"
        
        await status_message.edit_text(
            message_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            user_files = list_user_files(message.from_user.id)
            if user_files:
                files_list = "\n".join([f"• `{file}`" for file in user_files[:5]])
                await status_message.edit_text(
                    f"❌ *File not found:* `{file_name}`\n\n"
                    f"📁 *Your files:*\n\n{files_list}\n\n"
                    f"💡 Use exact filename from the list",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await status_message.edit_text(
                    f"❌ *File not found:* `{file_name}`\n\n"
                    f"You don't have any files uploaded yet\.",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await status_message.edit_text(f"❌ *S3 Error:* {error_code}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await status_message.edit_text(f"❌ *Error:* {str(e)}", parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("download"))
async def download_file_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(
            "Usage: `/download filename`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    local_path = f"./downloads/{file_name}"
    os.makedirs("./downloads", exist_ok=True)
    
    status_message = await message.reply_text(f"🔍 Looking for: `{file_name}`\.\.\.", parse_mode=ParseMode.MARKDOWN)
    
    try:
        s3_client.head_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        
        await asyncio.to_thread(
            s3_client.download_file,
            WASABI_BUCKET,
            user_file_name,
            local_path
        )
        
        await message.reply_document(
            document=local_path,
            caption=f"✅ *Downloaded:* `{file_name}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await status_message.delete()
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            user_files = list_user_files(message.from_user.id)
            if user_files:
                files_list = "\n".join([f"• `{file}`" for file in user_files[:5]])
                await status_message.edit_text(
                    f"❌ *File not found:* `{file_name}`\n\n"
                    f"📁 *Your files:*\n\n{files_list}",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await status_message.edit_text(
                    f"❌ *File not found:* `{file_name}`\n\n"
                    f"No files uploaded yet\.",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await status_message.edit_text(f"❌ *S3 Error:* {error_code}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await status_message.edit_text(f"❌ *Error:* {str(e)}", parse_mode=ParseMode.MARKDOWN)
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

@app.on_message(filters.command("list"))
async def list_files(client, message: Message):
    try:
        user_files = list_user_files(message.from_user.id)
        
        if not user_files:
            await message.reply_text("📂 You don't have any files uploaded yet\.", parse_mode=ParseMode.MARKDOWN)
            return
        
        files_list = "\n".join([f"• `{file}`" for file in user_files[:10]])
        
        if len(user_files) > 10:
            files_list += f"\n\n\.\.\.and {len(user_files) - 10} more files"
        
        await message.reply_text(
            f"📁 *Your files* \({len(user_files)} total\):\n\n{files_list}",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        await message.reply_text(f"❌ *Error:* {str(e)}", parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    help_text = (
        "🤖 *Wasabi Storage Bot Help*\n\n"
        "📤 *Upload files:* Just send me any file \(document, video, audio, photo\)\n"
        "📥 *Download:* `/download filename` \- Download a file\n"
        "🎬 *Play:* `/play filename` \- Get web player links\n"
        "📋 *List files:* `/list` \- Show your uploaded files\n"
        "❓ *Help:* `/help` \- Show this help message\n\n"
        "💡 *Tips:*\n"
        "• Filenames are case\-sensitive\n"
        "• Use `/list` to see exact filenames\n"
        "• Web player links expire in 1 hour\n"
        "• Direct download links expire in 24 hours\n\n"
        "🌐 *Web Player:* Files are accessible via Render web player"
    )
    await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

if __name__ == "__main__":
    print("🚀 Starting Wasabi Storage Bot with Render Web Player...")
    print(f"📊 Render URL: {RENDER_URL}")
    print(f"🌐 Web Player Port: {PORT}")
    
    # Test Wasabi connection
    try:
        s3_client.list_buckets()
        print("✅ Connected to Wasabi successfully")
    except Exception as e:
        print(f"❌ Wasabi connection failed: {e}")
        print("Please check your WASABI_ACCESS_KEY and WASABI_SECRET_KEY")
    
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    print("🤖 Starting Telegram Bot...")
    app.run()
