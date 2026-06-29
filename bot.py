import discord
from discord import app_commands
from discord.ext import commands
import requests
import json
import os
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

linked_accounts_file = "linked_accounts.json"
ROBLOX_API_URL = "https://inventory.roblox.com/v1/users/{user_id}/items/GamePass/{gamepass_id}"
CONFIG_FILE = "config.json"
ADMIN_ROLE_NAME = "Owner"  # Set your admin role name
OWNER_ID = 1201344036829671547  # Replace with your Discord user ID

# Load config
try:
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {"gamepass_roles": []}

# Load linked accounts
try:
    with open(linked_accounts_file, "r") as f:
        temp_accounts = json.load(f)
        if not isinstance(temp_accounts, dict) or ("discord_to_roblox" not in temp_accounts and "roblox_to_discord" not in temp_accounts):
            discord_to_roblox = {}
            roblox_to_discord = {}
            for discord_id, roblox_id in temp_accounts.items():
                discord_to_roblox[discord_id] = roblox_id
                roblox_to_discord[str(roblox_id)] = discord_id
            linked_accounts = {
                "discord_to_roblox": discord_to_roblox,
                "roblox_to_discord": roblox_to_discord,
                "force_linked_users": []
            }
        else:
            linked_accounts = temp_accounts
            if "force_linked_users" not in linked_accounts:
                linked_accounts["force_linked_users"] = []
except FileNotFoundError:
    linked_accounts = {"discord_to_roblox": {}, "roblox_to_discord": {}, "force_linked_users": []}


def save_linked_accounts():
    with open(linked_accounts_file, "w") as f:
        json.dump(linked_accounts, f, indent=2)


def is_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.get_role(discord.utils.get(interaction.guild.roles, name=ADMIN_ROLE_NAME).id)
        or interaction.user.id == OWNER_ID
    )


@bot.tree.command(name="link-roblox", description="Link your Roblox account to your Discord account.")
async def link_roblox(interaction: discord.Interaction, username: str):
    embed = discord.Embed(color=discord.Color.blue())
    user_id = await get_roblox_user_id(username)
    if user_id:
        roblox_id_str = str(user_id)
        if roblox_id_str in linked_accounts["roblox_to_discord"]:
            embed.title = "❌ Already Linked"
            embed.description = "This Roblox account is already linked to another Discord user."
            embed.color = discord.Color.red()
        else:
            discord_id = str(interaction.user.id)
            linked_accounts["discord_to_roblox"][discord_id] = user_id
            linked_accounts["roblox_to_discord"][roblox_id_str] = discord_id
            save_linked_accounts()
            embed.title = "✅ Account Linked"
            embed.description = f"Successfully linked to Roblox account: `{username}`"
            embed.color = discord.Color.green()
    else:
        embed.title = "❌ User Not Found"
        embed.description = f"Could not find a Roblox user with the username: `{username}`"
        embed.color = discord.Color.red()

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="unlink-roblox", description="Unlink your Roblox account from your Discord account.")
async def unlink_roblox(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)

    if discord_id in linked_accounts.get("force_linked_users", []):
        embed = discord.Embed(title="❌ Cannot Unlink", description="This account was force-linked by an admin and cannot be unlinked.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if discord_id in linked_accounts["discord_to_roblox"]:
        await remove_gamepass_roles(interaction.user)
        roblox_id = str(linked_accounts["discord_to_roblox"][discord_id])
        del linked_accounts["discord_to_roblox"][discord_id]
        del linked_accounts["roblox_to_discord"][roblox_id]
        save_linked_accounts()

        embed = discord.Embed(title="✅ Account Unlinked", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(title="❌ No Account Linked", description="You don't have any Roblox account linked.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="claim-roles", description="Claim your roles based on your Roblox gamepasses.")
async def claim_roles(interaction: discord.Interaction):
    embed = discord.Embed(color=discord.Color.blue())
    discord_id = str(interaction.user.id)

    if discord_id not in linked_accounts["discord_to_roblox"]:
        embed.title = "❌ Not Linked"
        embed.description = "You need to link your Roblox account first using `/link-roblox`!"
        embed.color = discord.Color.red()
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    roblox_id = linked_accounts["discord_to_roblox"][discord_id]

    added_roles = []
    already_has_roles = []
    missing_gamepasses = []

    for mapping in config["gamepass_roles"]:
        gamepass_id = mapping["gamepass_id"]
        role_id = mapping["role_id"]
        description = mapping["description"]
        role = interaction.guild.get_role(role_id)
        if role is None:
            continue
        if role in interaction.user.roles:
            already_has_roles.append(description)
            continue
        if await has_gamepass(roblox_id, gamepass_id):
            await interaction.user.add_roles(role)
            added_roles.append(description)
        else:
            missing_gamepasses.append(description)

    embed.title = "🎮 Role Claim"
    if added_roles:
        embed.description = "✅ Successfully claimed your roles!"
        embed.color = discord.Color.green()
    else:
        embed.description = "ℹ️ You have no roles to claim."
        embed.color = discord.Color.blue()

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ----------- ADMIN COMMANDS -----------

@bot.tree.command(name="list-linked", description="(Admin) List all linked accounts.")
@app_commands.checks.has_role(ADMIN_ROLE_NAME)
async def list_linked(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return

    description = ""
    for discord_id, roblox_id in linked_accounts["discord_to_roblox"].items():
        user = await bot.fetch_user(int(discord_id))
        description += f"<@{discord_id}> ➜ `{roblox_id}`\n"

    embed = discord.Embed(title="🔗 Linked Accounts", description=description or "None found.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="force-link", description="(Admin) Force link a user to a Roblox username.")
@app_commands.checks.has_role(ADMIN_ROLE_NAME)
async def force_link(interaction: discord.Interaction, discord_user: discord.User, roblox_username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return

    user_id = await get_roblox_user_id(roblox_username)
    if not user_id:
        await interaction.response.send_message("❌ Roblox user not found.", ephemeral=True)
        return

    discord_id = str(discord_user.id)
    roblox_id = str(user_id)

    linked_accounts["discord_to_roblox"][discord_id] = user_id
    linked_accounts["roblox_to_discord"][roblox_id] = discord_id
    if discord_id not in linked_accounts["force_linked_users"]:
        linked_accounts["force_linked_users"].append(discord_id)

    save_linked_accounts()
    await interaction.response.send_message(f"✅ Force linked {discord_user.mention} to `{roblox_username}`", ephemeral=True)


@bot.tree.command(name="admin-unlink", description="(Admin) Unlink a user manually.")
@app_commands.checks.has_role(ADMIN_ROLE_NAME)
async def admin_unlink(interaction: discord.Interaction, discord_user: discord.User):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return

    discord_id = str(discord_user.id)
    if discord_id in linked_accounts["discord_to_roblox"]:
        roblox_id = str(linked_accounts["discord_to_roblox"][discord_id])
        del linked_accounts["discord_to_roblox"][discord_id]
        del linked_accounts["roblox_to_discord"][roblox_id]
        if discord_id in linked_accounts["force_linked_users"]:
            linked_accounts["force_linked_users"].remove(discord_id)
        save_linked_accounts()
        await interaction.response.send_message(f"✅ Unlinked {discord_user.mention}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ User is not linked.", ephemeral=True)


# ----------- Helper Functions -----------

async def get_roblox_user_id(username: str) -> int:
    url = "https://users.roblox.com/v1/usernames/users"
    headers = {"Content-Type": "application/json"}
    data = json.dumps({"usernames": [username]})
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        user_data = response.json()
        if user_data["data"]:
            return user_data["data"][0]["id"]
    return None


async def has_gamepass(user_id: int, gamepass_id: int) -> bool:
    url = ROBLOX_API_URL.format(user_id=user_id, gamepass_id=gamepass_id)
    response = requests.get(url)
    if response.status_code == 200:
        gamepasses = response.json().get("data", [])
        return bool(gamepasses)
    return False


async def remove_gamepass_roles(member: discord.Member):
    role_ids = [mapping["role_id"] for mapping in config["gamepass_roles"]]
    roles_to_remove = [role for role in member.roles if role.id in role_ids]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove)


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

# Run bot
load_dotenv()
bot.run(os.getenv("DISCORD_TOKEN"))
