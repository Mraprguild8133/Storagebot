import os
import time
import boto3
import asyncio
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from urllib.parse import quote

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

# Initialize clients
app = Client("wasabi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

wasabi_endpoint_url = f'https://s3.{WASABI_REGION}.wasabisys.com'
s3_client = boto3.client(
    's3',
    endpoint_url=wasabi_endpoint_url,
    aws_access_key_id=WASABI_ACCESS_KEY,
    aws_secret_access_key=WASABI_SECRET_KEY
)

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

def create_web_player_html(file_name, presigned_url):
    """Create an HTML web player for the file"""
    # Determine file type for proper player
    if file_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
        player_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Player - {file_name}</title>
            <style>
                body {{ margin: 0; padding: 20px; background: #f0f0f0; font-family: Arial, sans-serif; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ margin-top: 0; color: #333; }}
                video {{ width: 100%; border-radius: 5px; }}
                .download-btn {{ display: inline-block; margin-top: 15px; padding: 10px 15px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{file_name}</h1>
                <video controls autoplay>
                    <source src="{presigned_url}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
                <br>
                <a href="{presigned_url}" class="download-btn" download>Download File</a>
            </div>
        </body>
        </html>
        """
    elif file_name.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
        player_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Player - {file_name}</title>
            <style>
                body {{ margin: 0; padding: 20px; background: #f0f0f0; font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ margin-top: 0; color: #333; }}
                audio {{ width: 100%; margin: 20px 0; }}
                .download-btn {{ display: inline-block; margin-top: 15px; padding: 10px 15px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{file_name}</h1>
                <audio controls autoplay>
                    <source src="{presigned_url}">
                    Your browser does not support the audio element.
                </audio>
                <br>
                <a href="{presigned_url}" class="download-btn" download>Download File</a>
            </div>
        </body>
        </html>
        """
    else:
        player_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Download - {file_name}</title>
            <style>
                body {{ margin: 0; padding: 20px; background: #f0f0f0; font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
                h1 {{ margin-top: 0; color: #333; }}
                .download-btn {{ display: inline-block; margin-top: 15px; padding: 15px 25px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; font-size: 18px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{file_name}</h1>
                <p>This file type cannot be previewed in the browser.</p>
                <a href="{presigned_url}" class="download-btn" download>Download File</a>
            </div>
        </body>
        </html>
        """
    
    return player_html

def upload_html_to_wasabi(html_content, file_name):
    """Upload HTML player to Wasabi"""
    try:
        html_key = f"players/{file_name}.html"
        s3_client.put_object(
            Bucket=WASABI_BUCKET,
            Key=html_key,
            Body=html_content,
            ContentType='text/html',
            ACL='public-read'
        )
        
        # Generate URL to the HTML player
        player_url = f"https://{WASABI_BUCKET}.s3.{WASABI_REGION}.wasabisys.com/{html_key}"
        return player_url
    except Exception as e:
        print(f"Error uploading HTML player: {e}")
        return None

def create_player_keyboard(file_name, presigned_url, web_player_url=None):
    """Create inline keyboard with player options"""
    keyboard = []
    
    if web_player_url:
        keyboard.append([InlineKeyboardButton("🌐 Web Player", url=web_player_url)])
    
    keyboard.extend([
        [InlineKeyboardButton("📥 Direct Download", url=presigned_url)],
    ])
    
    return InlineKeyboardMarkup(keyboard)

# Bot handlers
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "🚀 Cloud Storage Bot with Web Player\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename> to download files\n"
        "Use /play <filename> to get web player links\n"
        "Use /list to see your files"
    )

@app.on_message(filters.document | filters.video | filters.audio)
async def upload_file_handler(client, message: Message):
    media = message.document or message.video or message.audio
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
        
        # Create web player
        player_html = create_web_player_html(file_name, presigned_url)
        web_player_url = upload_html_to_wasabi(player_html, file_name)
        
        # Create keyboard with player options
        keyboard = create_player_keyboard(file_name, presigned_url, web_player_url)
        
        await status_message.edit_text(
            f"✅ Upload complete!\n\n"
            f"📁 File: {file_name}\n"
            f"📦 Size: {humanbytes(media.file_size)}\n"
            f"⏰ Link expires: 24 hours",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.on_message(filters.command("play"))
async def play_file_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /play <filename>")
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    
    status_message = await message.reply_text(f"Generating player for {file_name}...")
    
    try:
        # Check if file exists
        s3_client.head_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={'Bucket': WASABI_BUCKET, 'Key': user_file_name}, 
            ExpiresIn=86400
        )
        
        # Create web player
        player_html = create_web_player_html(file_name, presigned_url)
        web_player_url = upload_html_to_wasabi(player_html, file_name)
        
        # Create keyboard with player options
        keyboard = create_player_keyboard(file_name, presigned_url, web_player_url)
        
        await status_message.edit_text(
            f"🎬 Player ready for: {file_name}\n\n"
            f"⏰ Link expires: 24 hours",
            reply_markup=keyboard
        )

    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")

@app.on_message(filters.command("download"))
async def download_file_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /download <filename>")
        return

    file_name = " ".join(message.command[1:])
    user_file_name = f"{get_user_folder(message.from_user.id)}/{file_name}"
    local_path = f"./downloads/{file_name}"
    os.makedirs("./downloads", exist_ok=True)
    
    status_message = await message.reply_text(f"Downloading {file_name}...")
    
    try:
        # Download from Wasabi
        await asyncio.to_thread(
            s3_client.download_file,
            WASABI_BUCKET,
            user_file_name,
            local_path
        )
        
        # Send to user
        await message.reply_document(
            document=local_path,
            caption=f"Downloaded: {file_name}"
        )
        
        await status_message.delete()
        
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

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
        await message.reply_text(f"Error: {str(e)}")

if __name__ == "__main__":
    print("Starting Wasabi Storage Bot with Web Player...")
    app.run()