import discord
from discord import app_commands
import os
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
from pathlib import Path
import traceback
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ====== 確保 .env 一定被載入（重點）======
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("TOKEN")

# ====== SMTP 設定 ======
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

FIXED_RECIPIENT = "chuangyinezhe@gmail.com"

print("SMTP_USER:", SMTP_USER, flush=True)

# ====== Discord 設定 ======
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(discord.Client):
    def __init__(self, *, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        GUILD_ID = 1461250014381609002
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        await self.tree.sync()
        print("指令同步完成", flush=True)

bot = MyBot(intents=intents)

@bot.event
async def on_ready():
    print(f"Bot 上線：{bot.user}", flush=True)

# ====== 權限系統 ======
BASE_PATH = "/mnt/reports"

ROLE_PERMISSIONS = {
    "admin": {"upload"},
    "uploader": {"upload"},
    "viewer": set(),
}

IDENTITY_FILE = BASE_DIR / "identities.json"
DEFAULT_IDENTITY = "viewer"

def load_identity_map():
    if not IDENTITY_FILE.exists():
        return {}
    return json.load(open(IDENTITY_FILE))

async def has_permission(user_id, perm):
    data = load_identity_map()
    role = data.get(str(user_id), DEFAULT_IDENTITY)
    return perm in ROLE_PERMISSIONS.get(role, set())

# ====== SMTP 寄信 ======
async def send_email(subject, body, attachments):

    try:
        print("=== START SMTP ===", flush=True)

        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = FIXED_RECIPIENT
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        # ===== 檢查附件大小 =====
        total_size = sum(os.path.getsize(p) for _, p in attachments)
        total_mb = total_size / (1024 * 1024)

        print("Attachment MB:", total_mb, flush=True)

        if total_mb < 20:
            for filename, path in attachments:
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as f:
                    part.set_payload(f.read())

                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(part)
        else:
            msg.attach(MIMEText("\n⚠️ 附件過大，請至 NAS 查看", "plain"))

        def send():
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)

        await asyncio.to_thread(send)

        print("=== EMAIL SENT ===", flush=True)

    except Exception as e:
        print("=== EMAIL ERROR ===", flush=True)
        print(e, flush=True)
        traceback.print_exc()

# ====== Autocomplete ======
async def date_autocomplete(interaction, current):

    today = datetime.now()
    monday = today - timedelta(days=today.weekday())

    dates = [(monday - timedelta(weeks=i)).strftime("%Y%m%d") for i in range(10)]

    return [
        app_commands.Choice(name=d, value=d)
        for d in dates if current in d
    ]

# ====== 上傳指令 ======
@bot.tree.command(name="uploadfile")
@app_commands.autocomplete(日期=date_autocomplete)
async def uploadfile(
    interaction: discord.Interaction,
    日期: str,
    檔案1: discord.Attachment,
    檔案2: discord.Attachment | None = None,
):

    if not await has_permission(interaction.user.id, "upload"):
        await interaction.response.send_message("沒有權限")
        return

    await interaction.response.defer()

    target_dir = os.path.join(BASE_PATH, 日期)
    os.makedirs(target_dir, exist_ok=True)

    files = [f for f in [檔案1, 檔案2] if f]

    saved = []
    for f in files:
        path = os.path.join(target_dir, f.filename)
        await f.save(path)
        saved.append((f.filename, path))

    await interaction.followup.send("✅ 上傳完成，寄信中...")

    subject = f"新檔案上傳 ({日期})"
    body = f"使用者 {interaction.user} 上傳 {len(saved)} 個檔案"

    await send_email(subject, body, saved)

    await interaction.followup.send("📧 信件已送出")
    
# ====== 啟動 ======
bot.run(TOKEN)