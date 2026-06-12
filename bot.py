import discord
from discord import app_commands
from discord.ext import commands

from commands.admin import register_admin_commands
from commands.public import register_public_commands
from config.settings import Settings
from utils.discord_logs import log_error


PUBLIC_COMMAND_HELP = [
    '/tournament - Show active tournaments',
    '/fixtures - Show tournament fixtures',
    '/predict - Predict fixture score',
    '/predict_score_form - Predict with team-labelled score fields',
    '/predict_event - Predict goalscorer or red card',
    '/rules - Show scoring rules',
    '/leaderboard - Show leaderboard',
    '/profile - Show profile',
    '/predictions - Show predictions',
    '/set_visibility - Set prediction visibility',
]

ADMIN_COMMAND_HELP = [
    '/upsert_rules - Create or update scoring rules',
    '/add_tournament - Create or update tournament',
    '/update_fixture - Create or update fixture',
    '/update_score - Update final score and scoring',
    '/update_score_form - Update final score with team-labelled fields',
    '/recompute_points - Recompute score and event points for a fixture',
    '/update_event - Create or update fixture event and scoring',
]


def create_bot(settings: Settings):
    intents = discord.Intents.default()
    intents.message_content = False
    bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        if not getattr(bot, 'slash_commands_synced', False):
            synced_commands = await bot.tree.sync()
            bot.slash_commands_synced = True
            print(f'Synced {len(synced_commands)} slash commands')

        print(f'Logged in as {bot.user}')

    @bot.command(name='help')
    async def help_command(ctx):
        command_lines = list(PUBLIC_COMMAND_HELP)
        if ctx.author.id in settings.admin_user_ids:
            command_lines.extend(['', 'Private/admin commands:'])
            command_lines.extend(ADMIN_COMMAND_HELP)

        await ctx.send('```text\n' + '\n'.join(command_lines) + '\n```')

    @bot.tree.command(name='help', description='Show bot commands')
    async def slash_help(interaction: discord.Interaction):
        command_lines = list(PUBLIC_COMMAND_HELP)
        if interaction.user.id in settings.admin_user_ids:
            command_lines.extend(['', 'Private/admin commands:'])
            command_lines.extend(ADMIN_COMMAND_HELP)

        await interaction.response.send_message('```text\n' + '\n'.join(command_lines) + '\n```', ephemeral=True)

    @bot.event
    async def on_command_error(ctx, error):
        await log_error(
            bot,
            'Prefix command error',
            error,
            context=f'Command: {ctx.command}\nUser: {ctx.author} ({ctx.author.id})',
        )
        await ctx.send('Something went wrong while running that command.')

    async def on_app_command_error(interaction, error):
        if isinstance(error, app_commands.CommandInvokeError):
            original_error = error.original
        else:
            original_error = error

        await log_error(
            bot,
            'Slash command error',
            original_error,
            context=f'Command: {interaction.command}\nUser: {interaction.user} ({interaction.user.id})',
        )
        message = 'Something went wrong while running that command.'
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)

    bot.tree.on_error = on_app_command_error

    register_public_commands(bot)
    register_admin_commands(bot, settings)
    return bot
