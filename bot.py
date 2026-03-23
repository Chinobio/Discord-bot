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

# ====== 載入 .env ======
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

# ====== NAS ======
BASE_PATH = "/mnt/reports"

# ====== identity（只存 ID / 名字 / 權限） ======
IDENTITY_FILE = BASE_DIR / "identities.json"
DEFAULT_ROLE = "viewer"

ROLE_PERMISSIONS = {
    "admin": {"upload"},
    "uploader": {"upload"},
    "viewer": set(),
}

def load_identity_map():
    if not IDENTITY_FILE.exists():
        return {}
    try:
        with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_identity_map(data):
    with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def get_user_role(user_id):
    data = load_identity_map()
    user = data.get(str(user_id))
    if isinstance(user, dict):
        return user.get("role", DEFAULT_ROLE)
    return DEFAULT_ROLE

async def has_permission(user_id, perm):
    role = await get_user_role(user_id)
    return perm in ROLE_PERMISSIONS.get(role, set())

async def set_user_identity(user: discord.Member, role: str):
    data = load_identity_map()
    data[str(user.id)] = {
        "name": user.name,
        "role": role
    }
    save_identity_map(data)

def update_user_name(user: discord.User):
    data = load_identity_map()
    uid = str(user.id)

    if uid in data:
        data[uid]["name"] = user.name
        save_identity_map(data)

# ====== SMTP 寄信 ======
async def send_email(subject, body, attachments):
    try:
        print("=== START SMTP ===", flush=True)

        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = FIXED_RECIPIENT
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        # ===== 檢查大小 =====
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

# ====== upload 指令 ======
category_options = {
    "bigmeet": "大咪",
    "aitool": "AI工具",
    "article": "文章",
    "bookreport": "書籍報告",
    "sharepaper": "論文分享",
}

async def date_autocomplete(interaction: discord.Interaction, current: str):
    today = datetime.now()
    this_monday = today - timedelta(days=today.weekday())

    dates = [
        (this_monday - timedelta(weeks=i)).strftime("%Y%m%d")
        for i in range(15)
    ]

    return [
        app_commands.Choice(name=f"{d} (週一)", value=d)
        for d in dates
        if current in d
    ][:25]


@bot.tree.command(name="uploadfile", description="上傳到 NAS 並寄信")
@app_commands.autocomplete(日期=date_autocomplete)
@app_commands.choices(檔案類別=[
    app_commands.Choice(name=label, value=key)
    for key, label in category_options.items()
])
async def uploadfile(
    interaction: discord.Interaction,
    日期: str,
    檔案類別: app_commands.Choice[str],
    學生姓名: str,
    檔案1: discord.Attachment,
    檔案2: discord.Attachment | None = None,
    檔案3: discord.Attachment | None = None,
):
    if not await has_permission(interaction.user.id, "upload"):
        await interaction.response.send_message("❌ 沒有上傳權限")
        return

    await interaction.response.defer()

    update_user_name(interaction.user)

    category = 檔案類別.value
    category_label = 檔案類別.name

    if category == "bigmeet":
        target_dir = os.path.join(BASE_PATH, "bigmeet", 日期)
        logical_path = f"bigmeet/{日期}"
    else:
        target_dir = os.path.join(BASE_PATH, "smallmeet", category, 日期)
        logical_path = f"smallmeet/{category}/{日期}"

    os.makedirs(target_dir, exist_ok=True)

    files = [f for f in [檔案1, 檔案2, 檔案3] if f]

    saved = []
    total_size = 0

    for f in files:
        path = os.path.join(target_dir, f.filename)
        await f.save(path)
        saved.append((f.filename, path))
        total_size += f.size

    total_mb = round(total_size / (1024 * 1024), 2)
    file_list = "\n".join([f"- {name}" for name, _ in saved])

    await interaction.followup.send(
        f"✅ 上傳完成\n"
        f"📁 類別：{category_label}\n"
        f"📂 路徑：{logical_path}\n"
        f"📄 {len(saved)} 個檔案\n"
        f"📦 {total_mb} MB\n"
        f"{file_list}\n"
        f"📧 寄信中..."
    )

    subject = f"[{category_label}] 檔案上傳 ({日期})"

    body = f"""
Dear professor,
報告內容如以下附件

類別：{category_label}
日期：{日期}
學生 {學生姓名} 
敬上
""".strip()

    await send_email(subject, body, saved)

    await interaction.followup.send("📧 信件已寄出")
# ====== 設定身份 ======
@bot.tree.command(name="setidentity")
async def setidentity(
    interaction: discord.Interaction,
    使用者: discord.Member,
    身分: str
):
    await set_user_identity(使用者, 身分)
    await interaction.response.send_message(f"已設定 {使用者.name} 為 {身分}")

# ====== 啟動 ======
bot.run(TOKEN)