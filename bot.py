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
    檔案: discord.Attachment  # 單一檔案
):
    await interaction.response.defer(ephemeral=True)  # 延遲回應

    original_name = 檔案.filename.strip()

    # 1. 從檔名取出開頭 8 碼日期（如果有）
    date_match = re.match(r"^(\d{8})\s+", original_name)
    folder_date = date_match.group(1) if date_match else datetime.now().strftime("%Y%m%d")

    # 2. 決定資料夾路徑（用檔名日期）
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

    # 3. 建立資料夾（如果不存在）
    os.makedirs(target_dir, exist_ok=True)

    # 4. 清理檔名：去掉開頭日期 + 空白，空白換底線
    clean_name = re.sub(r"^\d{8}\s+", "", original_name)
    clean_name = clean_name.replace(" ", "_")
    final_filename = clean_name
    save_path = os.path.join(target_dir, final_filename)

    # 5. 儲存檔案
    await 檔案.save(save_path)

    file_size_mb = round(檔案.size / (1024 * 1024), 2)

    # 6. 準備回覆訊息（公開顯示）
    msg = (
        f"✅ **上傳成功**\n\n"
        f"類別：{檔案類別.name} ({檔案類別.value})\n"
        f"位置：`{logical_path}`\n"
        f"檔名：`{final_filename}`\n"
        f"大小：{file_size_mb} MB\n"
        f"上傳者：{interaction.user.mention}"
    )

    # 7. 預設寄信內容（給教授，簡單版）
    default_email_content = f"""
    教授好，
    
    已上傳新檔案：
    
    時間：{datetime.now().strftime("%Y-%m-%d %H:%M")}
    類別：{檔案類別.name} ({檔案類別.value})
    位置：{logical_path}
    檔名：{final_filename}
    
    如需查看，請至 NAS 對應資料夾。
    
    謝謝！
    """.strip()

    msg += "\n\n**預設寄信內容（可複製修改後寄給教授）：**\n```"
    msg += default_email_content
    msg += "```"

    # 改成公開顯示（大家都能看見）
    await interaction.followup.send(msg, ephemeral=False)
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