# bot.py
import discord
from discord import app_commands
import os
import json
from dotenv import load_dotenv
from datetime import datetime
import re
import resend
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# 載入 .env 檔案（裡面放你的 Token）
load_dotenv()
TOKEN = os.getenv("TOKEN")
NASgmail = os.getenv("NASgmail")
NASpassword = os.getenv("NASpassword")
NASURL = os.getenv("NASURL")

# 設定 intents（很重要！）
intents = discord.Intents.default()
intents.message_content = True   # 能讀取一般訊息內容
intents.members = True           # 能讀取成員資訊（視需求）

# 建立機器人實例（使用 commands.Bot 比較方便管理指令）
class MyBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

# 把這個加到你的 class MyBot 裡面（或直接替換原本的 setup_hook）
    async def setup_hook(self):
        print("開始同步指令...")

        # ←←← 把這裡換成你的伺服器 ID！（剛剛複製的那串數字）
        GUILD_ID = 1461250014381609002  # 例如：你的測試伺服器 ID

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        # 只同步這個伺服器（幾秒內生效）
        await self.tree.sync(guild=guild)

        print(f"指令已成功同步到伺服器 ID: {GUILD_ID}（幾秒後去 Discord 打 / 檢查）")
        # 正式上線時用這個（全域同步，會比較慢）
        await self.tree.sync()
        print("斜線指令已同步（全域）")

bot = MyBot(intents=intents)

# 機器人上線時觸發
@bot.event
async def on_ready():
    print(f"機器人已上線！登入為：{bot.user} (ID: {bot.user.id})")
    print("------")

# ==================== 指令區 ====================
# 上傳檔案
BASE_PATH = "/mnt/reports"
SMALLMEET_TYPES = {"aitool", "watchpaper", "bookreport", "article"}
IDENTITY_FILE = Path(__file__).resolve().parent / "identities.json"
IDENTITY_LOCK = asyncio.Lock()
DEFAULT_IDENTITY = "viewer"

ROLE_PERMISSIONS = {
    "admin": {"upload", "read", "create_folder", "manage_identity"},
    "uploader": {"upload", "read"},
    "viewer": {"read"},
}

AUTO_ROLE_BY_IDENTITY = {
    "admin": "Admin",
    "uploader": "Uploader",
    "viewer": "Viewer",
}

# Resend 設定
RESEND_API_KEY = os.getenv("RESEND_API_KEY")  # 從 .env 讀取
FIXED_RECIPIENT = "chuangyinezhe@gmail.com"     # ← 改成你要寄的 email
SENDER_EMAIL = "ailab@chuangyinezhe.dpdns.org"  # 從 Resend 取得的寄件人

# 如果沒有環境變數就印錯誤（開發用）
if not RESEND_API_KEY:
    print("警告：找不到 RESEND_API_KEY，請檢查 .env 檔案")

resend.api_key = RESEND_API_KEY

# ───────────────────────────────────────────────
# 指令本體
# ───────────────────────────────────────────────
BASE_PATH = "/mnt/reports"

CATEGORIES = {
    "大咪": "bigmeet",
    "AI工具": "aitool",
    "論文分享": "sharepaper",
    "報書": "bookreport",
    "文章": "article",
    "其他": "other",
}

BOOKREPORTLIST = {
    "Large Language Models A Deep Dive" : "Large Language Models A Deep Dive"
}


def load_identity_map() -> dict:
    if not IDENTITY_FILE.exists():
        return {}
    try:
        with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_identity_map(identity_map: dict) -> None:
    with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
        json.dump(identity_map, f, ensure_ascii=False, indent=2)


async def get_user_identity(user_id: int) -> str:
    async with IDENTITY_LOCK:
        identity_map = load_identity_map()
    return identity_map.get(str(user_id), DEFAULT_IDENTITY)


async def set_user_identity(user_id: int, identity: str) -> None:
    async with IDENTITY_LOCK:
        identity_map = load_identity_map()
        identity_map[str(user_id)] = identity
        save_identity_map(identity_map)


async def ensure_user_identity(user_id: int) -> str:
    async with IDENTITY_LOCK:
        identity_map = load_identity_map()
        uid = str(user_id)
        if uid not in identity_map:
            identity_map[uid] = DEFAULT_IDENTITY
            save_identity_map(identity_map)
        return identity_map[uid]


async def has_permission(user_id: int, permission: str) -> bool:
    identity = await get_user_identity(user_id)
    allowed = ROLE_PERMISSIONS.get(identity, set())
    return permission in allowed


async def apply_discord_role(member: discord.Member, identity: str) -> None:
    role_name = AUTO_ROLE_BY_IDENTITY.get(identity)
    if not role_name:
        return
    role = discord.utils.get(member.guild.roles, name=role_name)
    if not role:
        return
    if role in member.roles:
        return
    try:
        await member.add_roles(role, reason="Sync identity from bot JSON")
    except discord.Forbidden:
        pass


@bot.event
async def on_member_join(member: discord.Member):
    identity = await ensure_user_identity(member.id)
    await apply_discord_role(member, identity)

async def date_autocomplete(interaction: discord.Interaction, current: str):

    # 取得目前選的分類
    selected_category = None
    try:
        selected_category = interaction.namespace.檔案類別
    except AttributeError:
        pass

    # =====================================================
    # 📚 如果是 bookreport → 顯示書單
    # =====================================================
    if selected_category == "bookreport":

        filtered = [
            name for name in BOOKREPORTLIST.keys()
            if current.lower() in name.lower() or not current
        ]

        return [
            app_commands.Choice(name=name, value=name)
            for name in filtered[:25]
        ]

    # =====================================================
    # 📅 其他分類 → 顯示週一日期（原本邏輯）
    # =====================================================
    today = datetime.now()
    days_to_monday = today.weekday()
    this_monday = today - timedelta(days=days_to_monday)

    date_options = []
    for i in range(16):
        monday = this_monday - timedelta(weeks=i)
        date_str = monday.strftime("%Y%m%d")
        date_options.append(date_str)

    filtered = [
        date_str for date_str in date_options
        if current.lower() in date_str.lower() or not current
    ]

    return [
        app_commands.Choice(name=f"{d} (週一)", value=d)
        for d in filtered[:25]
    ]
async def send_email_async(params):
    try:
        await asyncio.to_thread(resend.Emails.send, params)
        print("EMAIL SENT")
    except Exception as e:
        print("EMAIL ERROR:", e)

@bot.tree.command(name="uploadfile", description="上傳到 NAS 並自動寄信")
@app_commands.describe(
    檔案類別="選擇分類",
    日期資料夾="選擇或輸入日期資料夾 (建議選週一日期)",
    檔案1="選擇第 1 個檔案",
    檔案2="選擇第 2 個檔案（可選）",
    檔案3="選擇第 3 個檔案（可選）",
    檔案4="選擇第 4 個檔案（可選）",
    檔案5="選擇第 5 個檔案（可選）"
)
@app_commands.choices(檔案類別=[
    app_commands.Choice(name=k, value=v) for k, v in CATEGORIES.items()
])
@app_commands.autocomplete(日期資料夾=date_autocomplete)
async def uploadfile(
    interaction: discord.Interaction,
    檔案類別: app_commands.Choice[str],
    日期資料夾: str,
    學生姓名: str,
    檔案1: discord.Attachment,
    檔案2: discord.Attachment | None = None,
    檔案3: discord.Attachment | None = None,
    檔案4: discord.Attachment | None = None,
    檔案5: discord.Attachment | None = None
):
    if not await has_permission(interaction.user.id, "upload"):
        await interaction.response.send_message("你目前沒有上傳權限。", ephemeral=False)
        return

    await interaction.response.defer()

    category_value = 檔案類別.value

    # 決定目標資料夾路徑
    if category_value == "bigmeet":
        target_dir = os.path.join(BASE_PATH, "bigmeet", 日期資料夾)
        logical_path = f"bigmeet/{日期資料夾}"
    else:
        target_dir = os.path.join(BASE_PATH, "smallmeet", category_value, 日期資料夾)
        logical_path = f"smallmeet/{category_value}/{日期資料夾}"

    # 自動建立資料夾（如果不存在）
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        await interaction.followup.send(f"建立資料夾失敗：{str(e)}", ephemeral=False)
        return

    upload_files = [f for f in [檔案1, 檔案2, 檔案3, 檔案4, 檔案5] if f is not None]
    if not upload_files:
        await interaction.followup.send("沒有收到檔案。", ephemeral=False)
        return

    uploaded_names = []
    total_size_bytes = 0
    saved_files = []

    for file in upload_files:
        final_filename = file.filename
        save_path = os.path.join(target_dir, final_filename)
        await file.save(save_path)
        uploaded_names.append(final_filename)
        total_size_bytes += file.size
        saved_files.append((final_filename, save_path))

    total_size_mb = round(total_size_bytes / (1024 * 1024), 2)
    file_list_text = "\n".join([f"- {name}" for name in uploaded_names])

    # Discord 回覆
    await interaction.followup.send(
        f"✅ 上傳完成\n"
        f"類別：{檔案類別.name}\n"
        f"資料夾：{logical_path}\n"
        f"檔案數：{len(uploaded_names)}\n"
        f"總大小：{total_size_mb} MB\n"
        f"檔案列表：\n{file_list_text}\n"
        f"上傳者：{interaction.user.mention}"
    )

    # ────────────────────────────────────────
    # 寄信部分保持原樣（以下不變）
    # ────────────────────────────────────────
    import base64
    email_attachments = []
    for filename, save_path in saved_files:
        with open(save_path, "rb") as f:
            file_base64 = base64.b64encode(f.read()).decode()
        email_attachments.append(
            {
                "filename": filename,
                "content": file_base64
            }
        )

    email_content = f"""
Dear professor,

已上傳新檔案：

類別：{檔案類別.name}
檔案數：{len(uploaded_names)}
檔案列表：
{file_list_text}

附件已附上，請查收。

學生 {學生姓名}
敬上
""".strip()

    params = {
        "from": "通知系統 <ailab@chuangyinezhe.dpdns.org>",
        "to": ["chuangyinezhe@gmail.com"],
        "subject": f"[{檔案類別.name}] 新檔案上傳 - 共 {len(uploaded_names)} 份",
        "text": email_content,
        "attachments": email_attachments
    }

    asyncio.create_task(send_email_async(params))


@bot.tree.command(name="setidentity", description="設定使用者身分（admin）")
@app_commands.describe(使用者="要設定的人", 身分="admin / uploader / viewer")
@app_commands.choices(身分=[
    app_commands.Choice(name="admin", value="admin"),
    app_commands.Choice(name="uploader", value="uploader"),
    app_commands.Choice(name="viewer", value="viewer"),
])
async def setidentity(
    interaction: discord.Interaction,
    使用者: discord.Member,
    身分: app_commands.Choice[str]
):
    if not await has_permission(interaction.user.id, "manage_identity"):
        await interaction.response.send_message("你沒有管理身分的權限。", ephemeral=False)
        return

    await set_user_identity(使用者.id, 身分.value)
    await apply_discord_role(使用者, 身分.value)
    await interaction.response.send_message(
        f"已設定 {使用者.mention} 身分為 `{身分.value}`。",
        ephemeral=False
    )


@bot.tree.command(name="myidentity", description="查看自己的身分與權限")
async def myidentity(interaction: discord.Interaction):
    identity = await ensure_user_identity(interaction.user.id)
    perms = sorted(ROLE_PERMISSIONS.get(identity, set()))
    perms_text = ", ".join(perms) if perms else "無"
    await interaction.response.send_message(
        f"你的身分：`{identity}`\n可用權限：{perms_text}",
        ephemeral=False
    )


@bot.tree.command(name="downloadfile", description="從 NAS 下載檔案（依身分控管）")
@app_commands.describe(分類="例如 bigmeet 或 smallmeet", 路徑="資料夾路徑", 檔名="檔案名稱")
async def downloadfile(
    interaction: discord.Interaction,
    分類: str,
    路徑: str,
    檔名: str
):
    if not await has_permission(interaction.user.id, "read"):
        await interaction.response.send_message("你目前沒有讀取權限。", ephemeral=False)
        return

    base = Path(BASE_PATH).resolve()
    target_dir = (base / 分類 / 路徑).resolve()

    if base not in target_dir.parents and target_dir != base:
        await interaction.response.send_message("路徑不合法。", ephemeral=False)
        return

    safe_name = Path(檔名).name
    target_file = (target_dir / safe_name).resolve()

    if target_dir not in target_file.parents:
        await interaction.response.send_message("檔名不合法。", ephemeral=False)
        return

    if not target_file.exists() or not target_file.is_file():
        await interaction.response.send_message("找不到指定檔案。", ephemeral=False)
        return

    if target_file.stat().st_size > 25 * 1024 * 1024:
        await interaction.response.send_message("檔案超過 25MB，無法直接傳送。", ephemeral=False)
        return

    await interaction.response.send_message(file=discord.File(str(target_file)))

# =============================================================================
@bot.tree.command(name = "createfolder", description = "建立每周新的資料夾")
async def createfolder(
    interaction: discord.Interaction,
    日期: str = None
):
    if not await has_permission(interaction.user.id, "create_folder"):
        await interaction.response.send_message("你目前沒有建立資料夾權限。", ephemeral=False)
        return

    await interaction.response.defer(ephemeral=False)
# 路徑設定
    BASE_PATH = "/mnt/reports"
    needcreatefolder = ["bigmeet", "aitool", "article","sharepaper"]
    if 日期:
        folder_date = 日期
    else:
        folder_date = datetime.now().strftime("%Y%m%d")
    for i in needcreatefolder:
        if i == "bigmeet":
            target_dir = os.path.join(BASE_PATH, "bigmeet", folder_date)
        else:
            target_dir = os.path.join(BASE_PATH, "smallmeet", i, folder_date)
        os.makedirs(target_dir, exist_ok=True)
    msg = f"✅ 已建立 {folder_date} 的資料夾結構！"
    await interaction.followup.send(msg, ephemeral=False)
    
# 一個簡單的 help 指令（超實用！）
@bot.tree.command(name="help", description="顯示所有可用指令")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="機器人指令列表", color=discord.Color.blue())
    for cmd in bot.tree.walk_commands():
        embed.add_field(
            name=f"/{cmd.name}",
            value=cmd.description or "沒有說明",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=False)


# 啟動機器人
if __name__ == "__main__":
    bot.run(TOKEN)
