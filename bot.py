import discord
from discord import app_commands
from discord.ext import commands

from commands.admin import register_admin_commands
from commands.public import register_public_commands
from config.settings import Settings
from services.announcement_scheduler import start_announcement_scheduler
from utils.discord_logs import log_error, push_admin_log


PUBLIC_COMMAND_HELP = [
    {
        'name': '1. Start Here',
        'value': (
            '**/tournament**\n'
            'Show active tournaments and their tournament codes.\n'
            'Use this first when you do not know the code.\n'
            'Example: `/tournament`\n\n'
            '**/rules tournament_code:WC26**\n'
            'Show scoring rules for a tournament.\n'
            'Example: `/rules tournament_code:WC26`'
        ),
    },
    {
        'name': '2. Find Fixtures',
        'value': (
            '**/fixtures tournament_code:WC26 fixture_filter:open**\n'
            'Show fixtures you can still predict. Only you can see the result.\n'
            'Filters: `all`, `predicted`, `open`.\n'
            'Example: `/fixtures tournament_code:WC26 fixture_filter:open`'
        ),
    },
    {
        'name': '3. Make Predictions',
        'value': (
            '**/predict fixture_id:12 home_score:2 away_score:1**\n'
            'Predict one exact score.\n\n'
            '**/predict_form count:5 tournament_code:WC26 start_fixture_id:12**\n'
            'Guided prediction flow for up to 5 open fixtures. Each fixture opens a form for scores and optional goalscorer.\n\n'
            '**/predict_event fixture_id:12 event_type:goalscorer player_name:Messi**\n'
            'Predict a goalscorer or red card for one fixture.'
        ),
    },
    {
        'name': '4. Track Results',
        'value': (
            '**/profile**\n'
            'Show your points and ranks.\n'
            'Example: `/profile`\n\n'
            '**/leaderboard tournament_code:WC26 point_filter:total**\n'
            'Show leaderboard. Filters: `total`, `event`, `prediction`.\n'
            'Example: `/leaderboard tournament_code:WC26 point_filter:total`'
        ),
    },
    {
        'name': '5. Privacy',
        'value': (
            '**/predictions user:@name tournament_code:WC26**\n'
            'Show your predictions or another user\'s public predictions.\n\n'
            '**/set_visibility visibility:private**\n'
            'Choose whether other users can see your predictions.'
        ),
    },
]

ADMIN_COMMAND_HELP = [
    {
        'name': 'Admin: Setup',
        'value': (
            '**/add_tournament name:World Cup code:WC26**\n'
            'Create or update a tournament.\n\n'
            '**/upsert_rules name:default config_json:{...}**\n'
            'Create or update scoring rules.\n\n'
            '**/update_fixture tournament_code:WC26 home_team:Mexico away_team:South Africa kickoff_at:2026-06-11T19:00:00Z**\n'
            'Create or update a fixture.'
        ),
    },
    {
        'name': 'Admin: Match Updates',
        'value': (
            '**/update_score fixture_id:12 home_score:2 away_score:1**\n'
            'Update final score and award score prediction points.\n\n'
            '**/update_score_form fixture_id:12**\n'
            'Update final score with team-labelled fields.\n\n'
            '**/update_event fixture_id:12 event_type:goal player_name:Messi team_name:Argentina**\n'
            'Record goals or red cards and award event points.'
        ),
    },
    {
        'name': 'Admin: Repairs',
        'value': (
            '**/recompute_points fixture_id:12**\n'
            'Recompute score and event points for a fixture.\n\n'
            '**/revert_score fixture_id:12**\n'
            'Clear final score and remove score points.\n\n'
            '**/revert_event fixture_id:12 event_type:goal**\n'
            'Remove all actual events of that type for the fixture and recompute event points.'
        ),
    },
    {
        'name': 'Admin: Announcements',
        'value': (
            '**/upsert_announcement announcement_type:fixture_announcement_2_days trigger_gap:1440**\n'
            'Configure scheduled fixture announcements.\n\n'
            '**/announcement_status**\n'
            'Check scheduler state and next trigger.\n\n'
            '**/run_announcement_now announcement_type:fixture_announcement_2_days**\n'
            'Run fixture announcement immediately.\n\n'
            '**/announce_release_notes**\n'
            'Post current release notes.'
        ),
    },
]


def _help_embeds(include_admin=False):
    embed = discord.Embed(
        title='Football Predictor Help',
        description='Suggested flow: find tournament, inspect fixtures, predict, then track points.',
        color=discord.Color.blue(),
    )
    for section in PUBLIC_COMMAND_HELP:
        embed.add_field(name=section['name'], value=section['value'], inline=False)

    embeds = [embed]
    if include_admin:
        admin_embed = discord.Embed(
            title='Admin Commands',
            description='Admin commands are hidden from non-admins and still checked against configured admin IDs.',
            color=discord.Color.red(),
        )
        for section in ADMIN_COMMAND_HELP:
            admin_embed.add_field(name=section['name'], value=section['value'], inline=False)
        embeds.append(admin_embed)
    return embeds


def create_bot(settings: Settings):
    intents = discord.Intents.default()
    intents.message_content = False
    bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        if not getattr(bot, 'slash_commands_synced', False):
            guild_command_counts = []
            for guild in bot.guilds:
                bot.tree.clear_commands(guild=guild)
                bot.tree.copy_global_to(guild=guild)
                guild_commands = await bot.tree.sync(guild=guild)
                guild_command_counts.append(f'{guild.name}: {len(guild_commands)}')

            bot.tree.clear_commands(guild=None)
            removed_global_commands = await bot.tree.sync()
            bot.slash_commands_synced = True
            sync_messages = [
                f'Removed global slash commands; {len(removed_global_commands)} remain globally.'
            ]
            if guild_command_counts:
                sync_messages.append(f'Synced guild slash commands: {", ".join(guild_command_counts)}.')
            await push_admin_log(bot, '\n'.join(sync_messages))
            start_announcement_scheduler(bot, settings)

        await push_admin_log(bot, f'Logged in as {bot.user}.')
    @bot.command(name='help')
    async def help_command(ctx):
        await ctx.send(embeds=_help_embeds(ctx.author.id in settings.admin_user_ids))

    @bot.tree.command(name='help', description='Show bot commands')
    async def slash_help(interaction: discord.Interaction):
        await interaction.response.send_message(
            embeds=_help_embeds(interaction.user.id in settings.admin_user_ids),
            ephemeral=True,
        )

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
