import asyncio
import logging

import discord

from services.announcement_service import AnnouncementService, FIXTURE_ANNOUNCEMENT_2_DAYS
from utils.discord_logs import push_admin_log


logger = logging.getLogger(__name__)


def start_announcement_scheduler(bot, settings):
    if getattr(bot, 'announcement_scheduler_started', False):
        return

    bot.announcement_scheduler_started = True
    bot.loop.create_task(_announcement_loop(bot, settings))


async def _announcement_loop(bot, settings):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await run_due_announcements(bot, settings)
        except Exception as error:
            logger.exception('Announcement scheduler failed')
            await push_admin_log(bot, f'Announcement scheduler failed: {error}')
        await asyncio.sleep(3600)


async def run_due_announcements(bot, settings):
    service = AnnouncementService()
    for announcement in service.due_announcements():
        if announcement['announcement_type'] == FIXTURE_ANNOUNCEMENT_2_DAYS:
            await send_fixture_announcements(bot, settings, service)
            service.mark_triggered(announcement['id'])


async def run_announcement_now(bot, settings, announcement_type):
    service = AnnouncementService()
    announcement = service.get_announcement_by_type(announcement_type)
    if announcement['announcement_type'] == FIXTURE_ANNOUNCEMENT_2_DAYS:
        await send_fixture_announcements(bot, settings, service)
        service.mark_triggered(announcement['id'])
        return f'Ran announcement {announcement_type}.'
    raise ValueError(f'Unsupported announcement type: {announcement_type}.')


async def send_fixture_announcements(bot, settings, service):
    groups = service.upcoming_fixture_groups()
    channel = bot.get_channel(settings.bot_announcement_channel_id)
    if channel is None:
        channel = await bot.fetch_channel(settings.bot_announcement_channel_id)

    if not groups:
        await channel.send('No fixtures in next 48hrs.')
        return

    for group in groups:
        embed = discord.Embed(
            title=f'{group["tournament_name"]} upcoming fixtures',
            color=discord.Color.teal(),
        )
        for fixture in group['fixtures']:
            embed.add_field(
                name=f'#{fixture["id"]}',
                value=f'{fixture["home_team"]} vs {fixture["away_team"]}',
                inline=False,
            )

        mention_chunks = _mention_chunks(group['users'])
        if not mention_chunks:
            await channel.send(
                content=f'Tournament {group["tournament_name"]} upcoming fixtures -',
                embed=embed,
            )
            continue

        for index, mentions in enumerate(mention_chunks):
            await channel.send(
                content=f'{mentions} tournament {group["tournament_name"]} upcoming fixtures -',
                embed=embed if index == 0 else None,
            )


def _mention_chunks(users, size=1800):
    chunks = []
    current = ''
    for user in users:
        mention = f'<@{user.discord_user_id}>'
        next_value = mention if not current else f'{current} {mention}'
        if len(next_value) > size:
            chunks.append(current)
            current = mention
        else:
            current = next_value
    if current:
        chunks.append(current)
    return chunks
