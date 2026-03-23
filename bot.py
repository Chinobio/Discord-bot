import asyncio
import json
import os
import smtplib
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("TOKEN")

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FIXED_RECIPIENT = "chuangyinezhe@gmail.com"

print("SMTP_USER:", SMTP_USER, flush=True)

GUILD_ID = 1461250014381609002

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class MyBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)

        # Rebuild guild commands from current code so old signatures do not linger.
        self.tree.clear_commands(guild=guild)
        self.tree.copy_global_to(guild=guild)
        guild_commands = await self.tree.sync(guild=guild)

        # Clear old global registrations with stale signatures.
        self.tree.clear_commands(guild=None)
        await self.tree.sync()

        print(f"指令同步完成，guild 指令數：{len(guild_commands)}", flush=True)


bot = MyBot(intents=intents)


@bot.event
async def on_ready():
    print(f"Bot 上線：{bot.user}", flush=True)


BASE_PATH = "/mnt/reports"
IDENTITY_FILE = BASE_DIR / "identities.json"
DEFAULT_ROLE = "viewer"
ROLE_CHOICES = ("admin", "uploader", "viewer")

ROLE_PERMISSIONS = {
    "admin": {"upload", "manage_roles"},
    "uploader": {"upload"},
    "viewer": set(),
}

CATEGORY_OPTIONS = {
    "bigmeet": "大會議",
    "aitool": "AI工具",
    "article": "文章",
    "bookreport": "讀書心得",
    "sharepaper": "論文分享",
}


def normalize_identity_entry(value):
    if isinstance(value, dict):
        return {
            "name": value.get("name", ""),
            "role": value.get("role", DEFAULT_ROLE),
        }
    if isinstance(value, str):
        return {
            "name": "",
            "role": value,
        }
    return {
        "name": "",
        "role": DEFAULT_ROLE,
    }


def load_identity_map():
    if not IDENTITY_FILE.exists():
        return {}

    try:
        with open(IDENTITY_FILE, "r", encoding="utf-8") as file:
            raw_data = json.load(file)
    except Exception:
        return {}

    return {
        user_id: normalize_identity_entry(value)
        for user_id, value in raw_data.items()
    }


def save_identity_map(data):
    with open(IDENTITY_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


async def get_user_role(user_id: int):
    data = load_identity_map()
    user = data.get(str(user_id), {})
    role = user.get("role", DEFAULT_ROLE)
    return role if role in ROLE_PERMISSIONS else DEFAULT_ROLE


async def has_permission(user_id: int, permission: str):
    role = await get_user_role(user_id)
    return permission in ROLE_PERMISSIONS.get(role, set())


async def set_user_identity(user: discord.Member, role: str):
    data = load_identity_map()
    data[str(user.id)] = {
        "name": user.display_name,
        "role": role,
    }
    save_identity_map(data)


def update_user_name(user: discord.abc.User):
    data = load_identity_map()
    user_id = str(user.id)
    entry = data.get(user_id)

    if entry is None:
        return

    entry["name"] = getattr(user, "display_name", user.name)
    data[user_id] = entry
    save_identity_map(data)


def build_upload_paths(category: str, upload_date: str):
    if category == "bigmeet":
        target_dir = os.path.join(BASE_PATH, "bigmeet", upload_date)
        logical_path = f"bigmeet/{upload_date}"
    else:
        target_dir = os.path.join(BASE_PATH, "smallmeet", category, upload_date)
        logical_path = f"smallmeet/{category}/{upload_date}"

    return target_dir, logical_path


async def send_email(subject: str, body: str, attachments):
    try:
        print("=== START SMTP ===", flush=True)

        message = MIMEMultipart()
        message["From"] = SMTP_USER
        message["To"] = FIXED_RECIPIENT
        message["Subject"] = str(Header(subject, "utf-8"))
        message.attach(MIMEText(body, "plain", "utf-8"))

        total_size = sum(os.path.getsize(path) for _, path in attachments)
        total_mb = total_size / (1024 * 1024)
        print("Attachment MB:", total_mb, flush=True)

        if total_mb < 20:
            for filename, path in attachments:
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as file:
                    part.set_payload(file.read())

                encoders.encode_base64(part)
                encoded_name = str(Header(filename, "utf-8"))
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{encoded_name}"',
                )
                message.attach(part)
        else:
            message.attach(
                MIMEText(
                    "\n附件總大小超過 20MB，因此本次信件不附檔，請改至 NAS 查看。",
                    "plain",
                    "utf-8",
                )
            )

        def send():
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(message)

        await asyncio.to_thread(send)
        print("=== EMAIL SENT ===", flush=True)

    except Exception as exc:
        print("=== EMAIL ERROR ===", flush=True)
        print(exc, flush=True)
        traceback.print_exc()
        raise


async def date_autocomplete(interaction: discord.Interaction, current: str):
    del interaction
    today = datetime.now()
    this_monday = today - timedelta(days=today.weekday())

    dates = [
        (this_monday - timedelta(weeks=index)).strftime("%Y%m%d")
        for index in range(15)
    ]

    return [
        app_commands.Choice(name=f"{date_value} (週一)", value=date_value)
        for date_value in dates
        if current in date_value
    ][:25]


def build_help_text(role: str):
    lines = [
        "可用指令如下：",
        "/help - 查看所有可用指令",
    ]

    if "upload" in ROLE_PERMISSIONS.get(role, set()):
        lines.append("/uploadfile - 上傳檔案到 NAS 並寄送通知信")

    if "manage_roles" in ROLE_PERMISSIONS.get(role, set()):
        lines.append("/setidentity - 設定成員權限（admin / uploader / viewer）")

    lines.append(f"你目前的權限是：{role}")
    return "\n".join(lines)


@bot.tree.command(name="uploadfile", description="上傳檔案到 NAS，並寄出通知信")
@app_commands.autocomplete(upload_date=date_autocomplete)
@app_commands.describe(
    upload_date="選擇週一日期，格式 YYYYMMDD",
    category="上傳分類",
    note="這次上傳的說明",
    file1="第一個附件",
    file2="第二個附件",
    file3="第三個附件",
)
@app_commands.choices(
    category=[
        app_commands.Choice(name=label, value=key)
        for key, label in CATEGORY_OPTIONS.items()
    ]
)
async def uploadfile(
    interaction: discord.Interaction,
    upload_date: str,
    category: app_commands.Choice[str],
    note: str,
    file1: discord.Attachment,
    file2: discord.Attachment | None = None,
    file3: discord.Attachment | None = None,
):
    if not await has_permission(interaction.user.id, "upload"):
        await interaction.response.send_message("你沒有上傳權限。", ephemeral=True)
        return

    await interaction.response.defer()
    update_user_name(interaction.user)

    category_key = category.value
    category_label = category.name
    target_dir, logical_path = build_upload_paths(category_key, upload_date)
    os.makedirs(target_dir, exist_ok=True)

    files = [attachment for attachment in (file1, file2, file3) if attachment]
    saved_files = []
    total_size = 0

    for attachment in files:
        save_path = os.path.join(target_dir, attachment.filename)
        await attachment.save(save_path)
        saved_files.append((attachment.filename, save_path))
        total_size += attachment.size

    total_mb = round(total_size / (1024 * 1024), 2)
    file_list = "\n".join(f"- {filename}" for filename, _ in saved_files)

    await interaction.followup.send(
        "檔案已上傳完成。\n"
        f"分類：{category_label}\n"
        f"路徑：{logical_path}\n"
        f"檔案數：{len(saved_files)}\n"
        f"總大小：{total_mb} MB\n"
        f"{file_list}\n"
        "正在寄送通知信..."
    )

    subject = f"[{category_label}] 檔案已上傳 ({upload_date})"
    body = (
        "Dear professor,\n\n"
        "以下是本次上傳內容，敬請查收。\n\n"
        f"分類：{category_label}\n"
        f"日期：{upload_date}\n"
        f"學生 {interaction.user.display_name}\n敬上"
    )

    try:
        await send_email(subject, body, saved_files)
        await interaction.followup.send("通知信已寄出。")
    except Exception:
        await interaction.followup.send("檔案已上傳，但寄信失敗，請查看主控台錯誤訊息。")


@bot.tree.command(name="setidentity", description="設定成員權限")
@app_commands.describe(member="要設定的成員", role="選擇權限")
@app_commands.choices(
    role=[
        app_commands.Choice(name="admin", value="admin"),
        app_commands.Choice(name="uploader", value="uploader"),
        app_commands.Choice(name="viewer", value="viewer"),
    ]
)
async def setidentity(
    interaction: discord.Interaction,
    member: discord.Member,
    role: app_commands.Choice[str],
):
    if not await has_permission(interaction.user.id, "manage_roles"):
        await interaction.response.send_message("你沒有更改權限的權限。", ephemeral=True)
        return

    selected_role = role.value.lower().strip()
    if selected_role not in ROLE_CHOICES:
        await interaction.response.send_message(
            "角色只能是 admin、uploader 或 viewer。",
            ephemeral=True,
        )
        return

    await set_user_identity(member, selected_role)
    await interaction.response.send_message(
        f"已將 {member.display_name} 設定為 {selected_role}。"
    )


@bot.tree.command(name="help", description="查看所有可用指令")
async def help_command(interaction: discord.Interaction):
    role = await get_user_role(interaction.user.id)
    await interaction.response.send_message(build_help_text(role), ephemeral=True)


bot.run(TOKEN)
