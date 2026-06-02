import discord
from discord.ext import commands

from commands.admin import register_admin_commands
from commands.public import register_public_commands
from config.settings import Settings


def create_bot(settings: Settings):
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents)

    @bot.event
    async def on_ready():
        print(f'Logged in as {bot.user}')

    register_public_commands(bot)
    register_admin_commands(bot, settings)
    return bot
