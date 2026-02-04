# bot.py
import discord
from discord import app_commands
import os
from dotenv import load_dotenv
from datetime import datetime
import re
import resend
import asyncio

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
    "審論文": "watchpaper",
    "報書": "bookreport",
    "文章": "article",
    "其他": "other",
}

# === 日期資料夾 autocomplete ===
async def date_autocomplete(interaction: discord.Interaction, current: str):
    category = interaction.namespace.檔案類別

    if not category:
        return []

    cat_value = CATEGORIES.get(category.name)

    if cat_value == "bigmeet":
        base = os.path.join(BASE_PATH, "bigmeet")
    else:
        base = os.path.join(BASE_PATH, "smallmeet", cat_value)

    if not os.path.exists(base):
        return []

    folders = sorted(os.listdir(base), reverse=True)

    return [
        app_commands.Choice(name=f, value=f)
        for f in folders
        if current in f
    ][:50]  # 最多回傳 50 個選項

async def send_email_async(params):
    try:
        await asyncio.to_thread(resend.Emails.send, params)
        print("EMAIL SENT")
    except Exception as e:
        print("EMAIL ERROR:", e)

@bot.tree.command(name="uploadfile", description="上傳到 NAS 並自動寄信")
@app_commands.describe(
    檔案類別="選擇分類",
    日期資料夾="選擇已有日期資料夾",
    檔案="選擇檔案"
)
@app_commands.choices(檔案類別=[
    app_commands.Choice(name=k, value=v) for k, v in CATEGORIES.items()
])
@app_commands.autocomplete(日期資料夾=date_autocomplete)
async def uploadfile(
    interaction: discord.Interaction,
    檔案類別: app_commands.Choice[str],
    日期資料夾: str,
    檔案: discord.Attachment
):
    await interaction.response.defer()

    category = 檔案類別.value

    if category == "bigmeet":
        target_dir = os.path.join(BASE_PATH, "bigmeet", 日期資料夾)
        logical_path = f"bigmeet/{日期資料夾}"
    else:
        target_dir = os.path.join(BASE_PATH, "smallmeet", category, 日期資料夾)
        logical_path = f"smallmeet/{category}/{日期資料夾}"

    os.makedirs(target_dir, exist_ok=True)

    final_filename = 檔案.filename
    save_path = os.path.join(target_dir, final_filename)

    # === 存 NAS ===
    await 檔案.save(save_path)

    size_mb = round(檔案.size / 1024 / 1024, 2)

    # === Discord 回覆 ===
    await interaction.followup.send(
        f"✅ 上傳完成\n"
        f"類別：{檔案類別.name}\n"
        f"資料夾：{logical_path}\n"
        f"檔名：{final_filename}\n"
        f"大小：{size_mb} MB\n"
        f"上傳者：{interaction.user.mention}"
    )

    # ===============================
    # Resend 寄信
    # ===============================
    import base64
    with open(save_path, "rb") as f:
        file_base64 = base64.b64encode(f.read()).decode()

    email_content = f"""
Dear professor,

已上傳新檔案：

類別：{檔案類別.name}
檔名：{final_filename}
大小：{size_mb} MB
位置：{logical_path}

附件已附上，請查收。

學生 印哲
敬上
""".strip()

    params = {
    "from": "通知系統 <notify@chuangyinezhe.dpdns.org>",
    "to": ["chuangyinezhe@gmail.com"],
    "subject": f"[{檔案類別.name}] 新檔案上傳 - {final_filename}",
    "text": email_content,
    "attachments": [
        {
            "filename": final_filename,
            "content": file_base64
        }
    ]
}

# 🔥 背景寄信（不等待）
    asyncio.create_task(send_email_async(params))

# =============================================================================
@bot.tree.command(name = "createfolder", description = "建立每周新的資料夾")
async def createfolder(
    interaction: discord.Interaction,
    日期: str = None
):
    await interaction.response.defer(ephemeral=False)
# 路徑設定
    BASE_PATH = "/mnt/reports"
    needcreatefolder = ["bigmeet", "aitool", "watchpaper", "article"]
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


# 啟動機器人
if __name__ == "__main__":
    bot.run(TOKEN)