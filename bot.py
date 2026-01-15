# bot.py
import discord
from discord import app_commands
import os
from dotenv import load_dotenv

# 載入 .env 檔案（裡面放你的 Token）
load_dotenv()
TOKEN = os.getenv("TOKEN")

# 設定 intents（很重要！）
intents = discord.Intents.default()
intents.message_content = True   # 能讀取一般訊息內容
intents.members = True           # 能讀取成員資訊（視需求）

# 建立機器人實例（使用 commands.Bot 比較方便管理指令）
class MyBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # 這裡可以加 guild-specific sync（開發時超快）
        # 把 YOUR_GUILD_ID 換成你測試伺服器的 ID（右鍵伺服器圖示 → Copy Server ID）
        # guild = discord.Object(id=YOUR_GUILD_ID)
        # self.tree.copy_global_to(guild=guild)
        # await self.tree.sync(guild=guild)
        
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

@bot.tree.command(name="hello", description="跟機器人打個招呼")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("哈囉！我是你的機器人～", ephemeral=True)


@bot.tree.command(name="ping", description="檢查機器人延遲")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 目前延遲：**{latency}ms**")


@bot.tree.command(name="說", description="讓機器人幫你說話")
@app_commands.describe(內容="你要我說什麼？")
async def say(interaction: discord.Interaction, 內容: str):
    await interaction.response.send_message(內容)


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