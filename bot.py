import discord
from discord import app_commands
import hashlib
import os
import tempfile

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def get_sha256(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)

    return sha256.hexdigest()


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")
    print("Bot is ready!")


@tree.command(
    name="sha256",
    description="Calculate the SHA256 hash of an APK"
)
async def sha256_command(interaction: discord.Interaction, apk: discord.Attachment):

    if not apk.filename.lower().endswith(".apk"):
        await interaction.response.send_message(
            "❌ Please upload an `.apk` file.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    temp_path = None

    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".apk") as temp:
            temp_path = temp.name

        # Download attachment
        await apk.save(temp_path)

        # Calculate hash
        sha256 = get_sha256(temp_path)

        await interaction.followup.send(
            f"✅ **SHA256:**\n```text\n{sha256}\n```\n"
            f"📦 **File:** `{apk.filename}`"
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Calculation failed:\n```text\n{e}\n```"
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


client.run(TOKEN)
