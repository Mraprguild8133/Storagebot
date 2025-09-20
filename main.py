import os
import time
import boto3
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

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

def get_user_folder(user_id):
    return f"user_{user_id}"

# Bot handlers
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "🚀 Cloud Storage Bot\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename> to download files\n"
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
        file_name = f"{get_user_folder(message.from_user.id)}/{os.path.basename(file_path)}"
        
        # Upload to Wasabi
        await asyncio.to_thread(
            s3_client.upload_file,
            file_path,
            WASABI_BUCKET,
            file_name
        )
        
        # Generate shareable link
        presigned_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={'Bucket': WASABI_BUCKET, 'Key': file_name}, 
            ExpiresIn=86400
        )
        
        await status_message.edit_text(
            f"✅ Upload complete!\n\n"
            f"File: {os.path.basename(file_path)}\n"
            f"Size: {humanbytes(media.file_size)}\n"
            f"Link: {presigned_url}"
        )
        
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if os.path.exists(file_path):
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
        response = await asyncio.to_thread(
            s3_client.list_objects_v2, 
            Bucket=WASABI_BUCKET, 
            Prefix=user_prefix
        )
        
        if 'Contents' not in response:
            await message.reply_text("No files found")
            return
        
        files = [obj['Key'].replace(user_prefix, "") for obj in response['Contents']]
        files_list = "\n".join([f"• {file}" for file in files])
        
        await message.reply_text(f"Your files:\n\n{files_list}")
    
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")

if __name__ == "__main__":
    print("Starting Wasabi Storage Bot...")
    app.run()
