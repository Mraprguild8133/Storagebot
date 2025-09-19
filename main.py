import os, re, base64, time, asyncio, traceback
from pathlib import Path
from threading import Thread

import boto3
from boto3.s3.transfer import TransferConfig
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask, render_template

# Optional: uvloop for async speed boost
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# -----------------------------
# Environment Variables
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
missing = [k for k,v in required_env_vars.items() if not v and k!="RENDER_URL"]
if missing: raise Exception(f"Missing env vars: {missing}")

# -----------------------------
# Pyrogram Client
# -----------------------------
app = Client(
    "wasabi_bot",
    api_id=required_env_vars["API_ID"],
    api_hash=required_env_vars["API_HASH"],
    bot_token=required_env_vars["BOT_TOKEN"]
)

# -----------------------------
# Wasabi S3 Client
# -----------------------------
wasabi_url = f'https://s3.{required_env_vars["WASABI_REGION"]}.wasabisys.com'
s3_client = boto3.client(
    's3',
    endpoint_url=wasabi_url,
    aws_access_key_id=required_env_vars["WASABI_ACCESS_KEY"],
    aws_secret_access_key=required_env_vars["WASABI_SECRET_KEY"]
)

# -----------------------------
# Flask App
# -----------------------------
flask_app = Flask(__name__, template_folder="templates")
@flask_app.route("/player/<media_type>/<encoded_url>")
def player(media_type, encoded_url):
    return render_template("player.html", media_type=media_type, encoded_url=encoded_url)
def run_flask(): flask_app.run(host="0.0.0.0", port=8000, use_reloader=False)

# -----------------------------
# Constants & Helpers
# -----------------------------
MAX_FILE_SIZE = 4000*1024*1024
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
MEDIA_EXTENSIONS = {
    'video':['.mp4','.mov','.avi','.mkv','.webm','.m4v'],
    'audio':['.mp3','.m4a','.ogg','.wav','.flac'],
    'image':['.jpg','.jpeg','.png','.gif','.bmp','.webp']
}

def humanbytes(size):
    if not size: return "0 B"
    for unit in ["B","KB","MB","GB","TB"]:
        if size<1024: return f"{size:.2f} {unit}"
        size/=1024

def sanitize_filename(name,max_length=150):
    return re.sub(r'[^a-zA-Z0-9._-]', '_', name)[:max_length]

def get_user_folder(user_id): return f"user_{user_id}"

def get_file_type(filename):
    ext=os.path.splitext(filename)[1].lower()
    for t,exts in MEDIA_EXTENSIONS.items():
        if ext in exts: return t
    return 'other'

def generate_player_url(filename,presigned_url):
    if not required_env_vars["RENDER_URL"]: return None
    ftype=get_file_type(filename)
    if ftype in ['video','audio','image']:
        encoded=base64.urlsafe_b64encode(presigned_url.encode()).decode()
        return f"{required_env_vars['RENDER_URL']}/player/{ftype}/{encoded}"
    return None

# -----------------------------
# Thread-Safe Progress Callbacks
# -----------------------------
def download_progress(current, total, message, start_time, prefix="Downloading"):
    now = time.time()
    diff = max(now - start_time, 1)
    percentage = current * 100 / total
    speed = current / diff
    speed_mb = speed / (1024*1024)
    eta = (total - current)/speed if speed>0 else 0
    eta = time.strftime("%H:%M:%S", time.gmtime(eta))
    icon = "⚡" if speed_mb<20 else "⚡⚡" if speed_mb<50 else "🚀" if speed_mb<150 else "🔥 LIGHTNING"
    bar_len = 20
    filled = int(bar_len*percentage/100)
    bar = "█"*filled+"—"*(bar_len-filled)
    text=f"{prefix}...\n[{bar}] {percentage:.2f}%\n📦 {humanbytes(current)} / {humanbytes(total)}\n{icon} {speed_mb:.2f} MB/s\n⏳ ETA: {eta}"

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(message.edit_text(text))
    except RuntimeError:
        asyncio.run_coroutine_threadsafe(message.edit_text(text), asyncio.new_event_loop())

def upload_progress(chunk):
    upload_progress.current += chunk
    now=time.time()
    diff=max(now-upload_progress.start_time,1)
    speed=upload_progress.current/diff
    speed_mb=speed/(1024*1024)
    percentage=upload_progress.current*100/upload_progress.total
    eta=(upload_progress.total-upload_progress.current)/speed if speed>0 else 0
    eta=time.strftime("%H:%M:%S", time.gmtime(eta))
    icon="⚡" if speed_mb<20 else "⚡⚡" if speed_mb<50 else "🚀" if speed_mb<150 else "🔥 LIGHTNING"
    bar_len=20
    filled=int(bar_len*percentage/100)
    bar="█"*filled+"—"*(bar_len-filled)
    text=f"☁️ Uploading...\n[{bar}] {percentage:.2f}%\n📦 {humanbytes(upload_progress.current)} / {humanbytes(upload_progress.total)}\n{icon} {speed_mb:.2f} MB/s\n⏳ ETA: {eta}"
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(upload_progress.message.edit_text(text))
    except RuntimeError:
        asyncio.run_coroutine_threadsafe(upload_progress.message.edit_text(text), asyncio.new_event_loop())

# -----------------------------
# Telegram Bot Handlers
# -----------------------------
@app.on_message(filters.command("start"))
async def start_command(client,message:Message):
    text="🚀 **Cloud Storage Bot**\n\nSend files to upload to Wasabi storage\nUse /download <filename> to download\nUse /list to see your files\nUse /play <filename> to get player link\n⚠️ Max file size: 4GB"
    if required_env_vars["RENDER_URL"]: text+="\n\n🎥 Web player enabled!"
    await message.reply_text(text)

@app.on_message(filters.document|filters.video|filters.audio|filters.photo)
async def upload_file_handler(client,message:Message):
    media=message.document or message.video or message.audio or (message.photo[-1] if message.photo else None)
    if not media: return await message.reply_text("Unsupported file type")
    size=getattr(media,"file_size",None)
    if size and size>MAX_FILE_SIZE: return await message.reply_text(f"File too large. Max: {humanbytes(MAX_FILE_SIZE)}")
    status=await message.reply_text("Starting download...")
    start_time=time.time()
    try:
        # Download
        file_path_str = await message.download(
            file_name=DOWNLOAD_DIR,
            progress=download_progress,
            progress_args=(status,start_time,"Downloading")
        )
        file_path = Path(file_path_str)
        file_name=sanitize_filename(file_path.name)
        user_file_name=f"{get_user_folder(message.from_user.id)}/{file_name}"

        # Upload
        upload_progress.current=0
        upload_progress.total=size
        upload_progress.start_time=time.time()
        upload_progress.message=status
        config=TransferConfig(
            multipart_threshold=64*1024*1024,
            multipart_chunksize=64*1024*1024,
            max_concurrency=25,
            use_threads=True
        )
        await asyncio.to_thread(
            s3_client.upload_file,
            str(file_path),
            required_env_vars["WASABI_BUCKET"],
            user_file_name,
            Callback=upload_progress,
            Config=config
        )

        presigned_url=s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket':required_env_vars["WASABI_BUCKET"],'Key':user_file_name},
            ExpiresIn=86400
        )
        player_url=generate_player_url(file_name,presigned_url)
        resp=f"✅ Upload complete!\n\n📂 File: {file_name}\n📦 Size: {humanbytes(size) if size else 'N/A'}\n🔗 Direct Link: {presigned_url}"
        if player_url: resp+=f"\n\n🎥 Player URL: {player_url}"
        await status.edit_text(resp)
    except Exception as e:
        print(traceback.format_exc())
        await status.edit_text(f"❌ Error: {str(e)}")
    finally:
        try: os.remove(file_path)
        except: pass

# -----------------------------
# Run Flask + Bot
# -----------------------------
if __name__=="__main__":
    Thread(target=run_flask,daemon=True).start()
    print("🚀 Starting Wasabi Storage Bot at INSTANT SPEED...")
    app.run()
                                         
