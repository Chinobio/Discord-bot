# bot.py
import discord
from discord import app_commands
import os
from dotenv import load_dotenv
from datetime import datetime
import re


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
@bot.tree.command(name="uploadfile", description="上傳到雲端網站")
@app_commands.describe(
    檔案類別="請選擇你的檔案類型（下拉選單）",
    檔案="上傳你的 PPT 檔案（.ppt 或 .pptx 或 .pdf）"
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
    await interaction.response.defer(ephemeral=True)

    today = datetime.now().strftime("%Y%m%d")
    category_value = 檔案類別.value

    # 1) 決定路徑：bigmeet vs smallmeet/{subtype}
    if category_value == "bigmeet":
        target_dir = os.path.join(BASE_PATH, "bigmeet", today)
        logical_path = f"bigmeet/{today}"
    elif category_value in SMALLMEET_TYPES:
        target_dir = os.path.join(BASE_PATH, "smallmeet", category_value, today)
        logical_path = f"smallmeet/{category_value}/{today}"
    else:
        # 其他 → 你也可以決定要放 smallmeet/other
        target_dir = os.path.join(BASE_PATH, "smallmeet", "other", today)
        logical_path = f"smallmeet/other/{today}"

    # 2) 建資料夾（不存在就建立）
    os.makedirs(target_dir, exist_ok=True)

    # 3) 檔名：日期_原始檔名
    original_name = 檔案.filename.strip()

    # 移除開頭的：8 碼日期 + 一個以上空白
    # 例：20260119 XXX.pdf -> XXX.pdf
    clean_name = re.sub(r"^\d{8}\s+", "", original_name)

    # 如果你不希望檔名有空白（選擇性）
    clean_name = clean_name.replace(" ", "_")

    final_filename = clean_name
    save_path = os.path.join(target_dir, final_filename)

    # 4) 寫入 NAS
    await 檔案.save(save_path)

    file_size_mb = round(檔案.size / (1024 * 1024), 2)

    msg = (
        f"✅ **上傳成功**\n\n"
        f"📂 類別：{檔案類別.name} ({檔案類別.value})\n"
        f"📁 位置：`{logical_path}`\n"
        f"📄 檔名：`{final_filename}`\n"
        f"📦 大小：{file_size_mb} MB"
    )
    await interaction.followup.send(msg)
# =============================================================================
# ===============================
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