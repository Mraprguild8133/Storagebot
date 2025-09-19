import os
import asyncio
import re
import json
import base64
import traceback
import boto3
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

required_env_vars = {
    "API_ID": os.getenv("API_ID"),
    "API_HASH": os.getenv("API_HASH"),
    "BOT_TOKEN": os.getenv("BOT_TOKEN"),
    "WASABI_ACCESS_KEY": os.getenv("WASABI_ACCESS_KEY"),
    "WASABI_SECRET_KEY": os.getenv("WASABI_SECRET_KEY"),
    "WASABI_BUCKET": os.getenv("WASABI_BUCKET"),
    "WASABI_REGION": os.getenv("WASABI_REGION"),
    "RENDER_URL": os.getenv("RENDER_URL", "").rstrip('/')
}

missing_vars = [var for var, value in required_env_vars.items() if not value and var != "RENDER_URL"]
if missing_vars:
    raise Exception(f"Missing environment variables: {', '.join(missing_vars)}")

# Init bot + Wasabi
app = Client("wasabi_bot",
    api_id=required_env_vars["API_ID"],
    api_hash=required_env_vars["API_HASH"],
    bot_token=required_env_vars["BOT_TOKEN"]
)

s3_client = boto3.client(
    's3',
    endpoint_url=f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com',
    aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
    aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"]
)

# Constants
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MEDIA_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'],
    'audio': ['.mp3', '.m4a', '.ogg', '.wav', '.flac'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
}

# Helpers
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

def get_user_folder(user_id): return f"user_{user_id}"

def sanitize_filename(filename, max_length=150):
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return filename[:max_length]

def get_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    for t, exts in MEDIA_EXTENSIONS.items():
        if ext in exts: return t
    return 'other'

def generate_player_url(filename, presigned_url):
    if not required_env_vars["RENDER_URL"]: return None
    file_type = get_file_type(filename)
    if file_type in ['video', 'audio', 'image']:
        encoded = base64.urlsafe_b64encode(presigned_url.encode()).decode().rstrip("=")
        return f"{required_env_vars['RENDER_URL']}/player/{file_type}/{encoded}"
    return None

# Commands
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    txt = (
        "🚀 **Cloud Storage Bot**\n\n"
        "Send me any file to upload to Wasabi storage\n"
        "Use /download <filename>\n"
        "Use /list to see your files\n"
        "Use /play <filename> to get a web player link\n\n"
        f"⚠️ Max size: {humanbytes(MAX_FILE_SIZE)}"
    )
    if required_env_vars["RENDER_URL"]:
        txt += "\n\n🎥 Web player support is enabled!"
    await message.reply_text(txt)

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def upload_file_handler(client, message: Message):
    media = message.document or message.video or message.audio or message.photo
    if not media:
        await message.reply_text("Unsupported file type")
        return
    size = getattr(media, "file_size", None)
    if size and size > MAX_FILE_SIZE:
        await message.reply_text(f"File too large. Max {humanbytes(MAX_FILE_SIZE)}")
        return
    status = await message.reply_text("⬇️ Downloading...")
    try:
        file_path = await message.download()
        file_name = sanitize_filename(os.path.basename(file_path))
        user_file = f"{get_user_folder(message.from_user.id)}/{file_name}"

        await asyncio.to_thread(s3_client.upload_file, file_path, required_env_vars["WASABI_BUCKET"], user_file)

        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file},
            ExpiresIn=86400
        )
        player_url = generate_player_url(file_name, presigned_url)

        resp = f"✅ Uploaded!\n\n📂 {file_name}\n📏 {humanbytes(size)}\n🔗 {presigned_url}"
        if player_url:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Web Player", url=player_url)]])
            await status.edit_text(resp, reply_markup=kb)
        else:
            await status.edit_text(resp)
    except Exception:
        await status.edit_text(f"❌ Error:\n{traceback.format_exc()}")
    finally:
        try: os.remove(file_path)
        except: pass

@app.on_message(filters.command("download"))
async def download_file_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /download <filename>")
        return
    file_name = " ".join(message.command[1:])
    safe_name = sanitize_filename(file_name)
    user_file = f"{get_user_folder(message.from_user.id)}/{safe_name}"
    local_path = DOWNLOAD_DIR / safe_name
    status = await message.reply_text(f"⬇️ Downloading {file_name}...")
    try:
        await asyncio.to_thread(s3_client.download_file,
            required_env_vars["WASABI_BUCKET"], user_file, str(local_path))
        await message.reply_document(str(local_path), caption=f"📂 {file_name}")
        await status.delete()
    except Exception:
        await status.edit_text(f"❌ Error:\n{traceback.format_exc()}")
    finally:
        try: os.remove(local_path)
        except: pass

@app.on_message(filters.command("play"))
async def play_file_handler(client, message: Message):
    if not required_env_vars["RENDER_URL"]:
        await message.reply_text("❌ Web player not configured.")
        return
    if len(message.command) < 2:
        await message.reply_text("Usage: /play <filename>")
        return
    file_name = " ".join(message.command[1:])
    safe_name = sanitize_filename(file_name)
    user_file = f"{get_user_folder(message.from_user.id)}/{safe_name}"
    status = await message.reply_text(f"Generating player link...")
    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': required_env_vars["WASABI_BUCKET"], 'Key': user_file},
            ExpiresIn=86400
        )
        player_url = generate_player_url(file_name, presigned_url)
        if player_url:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Open in Player", url=player_url)]])
            await status.edit_text(f"Link for {file_name}:", reply_markup=kb)
        else:
            await status.edit_text("❌ Unsupported format.")
    except Exception:
        await status.edit_text(f"❌ Error:\n{traceback.format_exc()}")

@app.on_message(filters.command("list"))
async def list_files(client, message: Message):
    try:
        prefix = get_user_folder(message.from_user.id) + "/"
        resp = await asyncio.to_thread(s3_client.list_objects_v2,
            Bucket=required_env_vars["WASABI_BUCKET"], Prefix=prefix)
        if 'Contents' not in resp:
            await message.reply_text("📂 No files.")
            return
        files = []
        for obj in resp['Contents']:
            fn = obj['Key'].replace(prefix, "")
            if fn:
                ft = get_file_type(fn)
                icon = "🎥" if ft in ["video", "audio"] else "📄"
                files.append(f"{icon} {fn} ({humanbytes(obj['Size'])})")
        out = "\n".join(files)
        # split if > 4000 chars
        for i in range(0, len(out), 4000):
            await message.reply_text(out[i:i+4000])
    except Exception:
        await message.reply_text(f"❌ Error:\n{traceback.format_exc()}")

if __name__ == "__main__":
    print("🚀 Bot running...")
    app.run()
    
