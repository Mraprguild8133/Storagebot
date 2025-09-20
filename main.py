import os
import time
import boto3
import asyncio
import re
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
    
    # Wasabi requires special configuration
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
            region_name=WASABI_REGION
        )
        s3_client.head_bucket(Bucket=WASABI_BUCKET)
        logger.info("Successfully connected to Wasabi bucket with alternative endpoint")
    except Exception as alt_e:
        logger.error(f"Alternative connection also failed: {alt_e}")
        raise Exception(f"Could not connect to Wasabi: {alt_e}")

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

def create_download_keyboard(presigned_url):
    """Create inline keyboard with download option"""
    keyboard = [
        [InlineKeyboardButton("📥 Direct Download", url=presigned_url)],
    ]
    
    return InlineKeyboardMarkup(keyboard)

# Bot handlers
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "🚀 Cloud Storage Bot\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename> to download files\n"
        "Use /list to see your files"
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
        
        # Create keyboard with download option
        keyboard = create_download_keyboard(presigned_url)
        
        file_size = media.file_size if hasattr(media, 'file_size') else 0
        if message.photo:
            file_size = os.path.getsize(file_path)
        
        await status_message.edit_text(
            f"✅ Upload complete!\n\n"
            f"📁 File: {file_name}\n"
            f"📦 Size: {humanbytes(file_size)}\n"
            f"⏰ Link expires: 24 hours",
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
    
    status_message = await message.reply_text(f"Generating download link for {file_name}...")
    
    try:
        # Check if file exists
        s3_client.head_object(Bucket=WASABI_BUCKET, Key=user_file_name)
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={'Bucket': WASABI_BUCKET, 'Key': user_file_name}, 
            ExpiresIn=86400
        )
        
        # Create keyboard with download option
        keyboard = create_download_keyboard(presigned_url)
        
        await status_message.edit_text(
            f"📥 Download ready for: {file_name}\n\n"
            f"⏰ Link expires: 24 hours",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_message.edit_text(f"Error: {str(e)}")

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

if __name__ == "__main__":
    print("Starting Wasabi Storage Bot...")
    app.run()
