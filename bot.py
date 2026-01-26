# bot.py
import discord
from discord import app_commands
import os
from dotenv import load_dotenv
from datetime import datetime
import re
import resend

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
@bot.tree.command(name="uploadfile", description="上傳到雲端網站（單一檔案）")
@app_commands.describe(
    檔案類別="請選擇你的檔案類型（下拉選單）",
    檔案="上傳你的檔案（.ppt .pptx .pdf）"
)
@app_commands.choices(檔案類別=[
    app_commands.Choice(name="大咪", value="bigmeet"),
    app_commands.Choice(name="AI工具", value="aitool"),
    app_commands.Choice(name="審論文", value="watchpaper"),
    app_commands.Choice(name="報書", value="bookreport"),
    app_commands.Choice(name="文章", value="article"),
    app_commands.Choice(name="其他", value="other"),
])
async def uploadfile(
    interaction: discord.Interaction,
    檔案類別: app_commands.Choice[str],
    檔案: discord.Attachment
):
    await interaction.response.defer(ephemeral=False)

    original_name = 檔案.filename.strip()
    temp = original_name
    # 1. 從檔名取出開頭 8 碼日期
    date_match = re.match(r"^(\d{8})\s+", original_name)
    if date_match:
        folder_date = date_match.group(1)
        is_auto_date = False
    else:
        folder_date = datetime.now().strftime("%Y%m%d")
        is_auto_date = True

    # 2. 決定資料夾路徑
    category_value = 檔案類別.value
    if category_value == "bigmeet":
        target_dir = os.path.join(BASE_PATH, "bigmeet", folder_date)
        logical_path = f"bigmeet/{folder_date}"
    elif category_value in SMALLMEET_TYPES:
        target_dir = os.path.join(BASE_PATH, "smallmeet", category_value, folder_date)
        logical_path = f"smallmeet/{category_value}/{folder_date}"
    else:
        target_dir = os.path.join(BASE_PATH, "smallmeet", "other", folder_date)
        logical_path = f"smallmeet/other/{folder_date}"

    # 3. 檢查資料夾是否存在，不存在就建立
    folder_exists = os.path.exists(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    # 4. 清理檔名（砍掉前面日期和空格）
    clean_name = re.sub(r"^\d{8}\s+", "", original_name)
    final_filename = clean_name
    save_path = os.path.join(target_dir, final_filename)

    # 5. 儲存檔案到 NAS
    await 檔案.save(save_path)

    file_size_mb = round(檔案.size / (1024 * 1024), 2)

    # 6. 公開回覆訊息（簡單版）
    folder_status = "✨ 新建資料夾" if not folder_exists else "📁 既有資料夾"
    date_status = f"📅 檔名日期：{folder_date}" if not is_auto_date else f"📅 自動日期（無檔名日期）：{folder_date}"
    
    msg = (
        f"✅ **上傳成功**\n\n"
        f"類別：{檔案類別.name} ({檔案類別.value})\n"
        f"位置：`{logical_path}`\n"
        f"{folder_status}\n"
        f"{date_status}\n"
        f"檔名：`{final_filename}`\n"
        f"大小：{file_size_mb} MB\n"
        f"上傳者：{interaction.user.mention}"
        f"temp={temp}"
    )

    await interaction.followup.send(msg)

    # 7. 自動寄信（只帶附件 + CC）
    try:
        import base64

        # 讀取檔案並轉 base64
        with open(save_path, "rb") as f:
            file_bytes = f.read()
            file_base64 = base64.b64encode(file_bytes).decode('utf-8')

        # 簡單信件內容（可再改）
        email_content = f"""
Dear professor，

已上傳新檔案：
- 類別：{檔案類別.name}
- 檔名：{final_filename}
- 大小：{file_size_mb} MB
- 位置：{logical_path}

附件已附上，請查收。

謝謝！
        """.strip()

        params = {
            "from": "通知系統 <notify@chuangyinezhe.dpdns.org>",
            "to": ["chuangyinezhe@gmail.com"],          # 教授（主要收件人）
            # "cc": ["助教@gmail.com", "組員@gmail.com"],  # ← 改成你要 CC 的 email 清單，或留空 []
            "subject": f"[{檔案類別.name}] 新檔案上傳 - {final_filename}",
            "text": email_content,
            "attachments": [
                {
                    "filename": final_filename,
                    "content": file_base64
                }
            ]
        }

        email_result = resend.Emails.send(params)

        success_msg = f"📧 已自動寄通知信給教授（含附件）並 CC 相關人員（ID: {email_result['id']})"
        await interaction.channel.send(success_msg)

    except Exception as e:
        error_msg = f"⚠️ 寄信失敗：{str(e)}（但檔案已成功上傳）"
        await interaction.channel.send(error_msg)
# =============================================================================
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