from typing import Literal

import discord
from discord import app_commands

from config.constants import ADMIN_LOG_CHANNEL_URL
from services.announcement_service import AnnouncementService
from services.announcement_scheduler import run_announcement_now
from services.admin_score_update_service import AdminScoreUpdateService
from services.tournament_service import TournamentService
from release import APP_VERSION, RELEASE_NOTES
from utils.discord_logs import log_error, push_admin_log, push_channel_log, push_prediction_award_log


ADMIN_COMMAND_NAMES = {
    'upsert_rules',
    'upsert_announcement',
    'announcement_status',
    'run_announcement_now',
    'announce_release_notes',
    'add_tournament',
    'close_tournament',
    'update_fixture',
    'import_fixtures',
    'update_score',
    'update_score_form',
    'recompute_points',
    'revert_score',
    'revert_event',
    'update_event',
}


def _is_admin(interaction, settings):
    return interaction.user.id in settings.admin_user_ids


async def _deny_admin(interaction):
    await log_error(
        interaction.client,
        'Unauthorized private command attempt',
        context=f'Command: {interaction.command}\nUser: {interaction.user} ({interaction.user.id})',
    )
    await interaction.response.send_message('You do not have permission to use this command.', ephemeral=True)


async def _send_admin_error(interaction, error):
    await log_error(
        interaction.client,
        'Handled admin command error',
        error,
        context=f'Command: {interaction.command}\nUser: {interaction.user} ({interaction.user.id})',
    )
    if interaction.response.is_done():
        await interaction.followup.send(str(error), ephemeral=True)
        return
    await interaction.response.send_message(str(error), ephemeral=True)


async def _push_admin_log(interaction, message):
    await push_admin_log(interaction.client, f'{message}\nTriggered by: {interaction.user.mention}')


async def _active_tournament_autocomplete(interaction, current):
    tournament_service = TournamentService()
    return [
        app_commands.Choice(name=choice['name'], value=choice['value'])
        for choice in tournament_service.active_tournament_choices(current)
    ]


def _format_datetime(value):
    return 'N/A' if value is None else value.strftime('%Y-%m-%d %H:%M UTC')


def _fixture_log_label(fixture_id):
    try:
        fixture = TournamentService().get_fixture_details(fixture_id)
    except LookupError:
        return f'Fixture #{fixture_id}'
    if fixture['home_score'] is not None and fixture['away_score'] is not None:
        return (
            f'Fixture #{fixture["id"]} '
            f'{fixture["home_team"]} {fixture["home_score"]}-{fixture["away_score"]} {fixture["away_team"]}'
        )
    return f'Fixture #{fixture["id"]} {fixture["home_team"]} vs {fixture["away_team"]}'


async def _push_prediction_awards(interaction, fixture_id, prediction_type, awarded_users):
    if not awarded_users:
        return
    recipients = ', '.join(
        f'<@{user["discord_user_id"]}> (+{user["points"]})'
        for user in awarded_users
    )
    await push_prediction_award_log(
        interaction.client,
        f'{_fixture_log_label(fixture_id)} {prediction_type} prediction points awarded to: {recipients}',
    )


async def _push_prediction_point_losses(interaction, fixture_id, prediction_type, removed_users):
    if not removed_users:
        return
    recipients = ', '.join(
        f'<@{user["discord_user_id"]}> ({user["points"]})'
        for user in removed_users
    )
    await push_prediction_award_log(
        interaction.client,
        f'{_fixture_log_label(fixture_id)} {prediction_type} prediction points lost by: {recipients}',
    )


async def _push_prediction_removals(interaction, fixture_id, prediction_type, removed_users):
    if not removed_users:
        return
    recipients = ', '.join(
        f'<@{user["discord_user_id"]}> (-{user["points"]})'
        for user in removed_users
    )
    await push_prediction_award_log(
        interaction.client,
        f'{_fixture_log_label(fixture_id)} {prediction_type} prediction points removed from: {recipients}',
    )


def _parse_score(value, team_name):
    try:
        score = int(value)
    except ValueError as error:
        raise ValueError(f'{team_name} score must be a whole number.') from error
    if score < 0:
        raise ValueError(f'{team_name} score cannot be negative.')
    return score


async def _update_score_and_award(
    interaction,
    fixture_id,
    home_score,
    away_score,
    tournament_service,
    admin_score_update_service,
    red_card_given=None,
):
    fixture_message = tournament_service.update_fixture_score(
        {
            'fixture_id': fixture_id,
            'home_score': home_score,
            'away_score': away_score,
            'red_card_given': red_card_given,
        }
    )
    await _push_admin_log(interaction, fixture_message)
    score_result = admin_score_update_service.award_score_predictions_for_fixture(fixture_id)
    score_message = score_result['message']
    await _push_admin_log(interaction, score_message)
    await _push_prediction_awards(
        interaction,
        fixture_id,
        'score',
        score_result['awarded_users'],
    )
    event_result = admin_score_update_service.award_event_predictions_for_fixture(fixture_id)
    event_message = event_result['message']
    await _push_admin_log(interaction, event_message)
    await _push_prediction_awards(
        interaction,
        fixture_id,
        'event',
        event_result['awarded_users'],
    )
    await _push_prediction_point_losses(
        interaction,
        fixture_id,
        'event',
        event_result.get('removed_users', []),
    )
    leaderboard_message = admin_score_update_service.refresh_leaderboard_for_fixture(fixture_id)
    await _push_admin_log(interaction, leaderboard_message)
    return f'{fixture_message} {score_message} {event_message} {leaderboard_message}'


class FinalScoreModal(discord.ui.Modal):
    def __init__(
        self,
        fixture,
        tournament_service,
        admin_score_update_service,
        owner_id,
        fixtures=None,
        index=0,
    ):
        super().__init__(title=f'Update fixture #{fixture["id"]}')
        self.fixture = fixture
        self.tournament_service = tournament_service
        self.admin_score_update_service = admin_score_update_service
        self.owner_id = owner_id
        self.fixtures = fixtures or [fixture]
        self.index = index
        self.home_score = discord.ui.TextInput(
            label=f'{fixture["home_team"]} score'[:45],
            placeholder='0',
            default=str(fixture['home_score']) if fixture['home_score'] is not None else None,
            min_length=1,
            max_length=2,
        )
        self.away_score = discord.ui.TextInput(
            label=f'{fixture["away_team"]} score'[:45],
            placeholder='0',
            default=str(fixture['away_score']) if fixture['away_score'] is not None else None,
            min_length=1,
            max_length=2,
        )
        self.red_card_given = discord.ui.TextInput(
            label='Actual red card given? yes/no',
            placeholder='Optional. Blank leaves existing red-card-given value unchanged.',
            default=fixture.get('red_card_given'),
            required=False,
            max_length=5,
        )
        self.add_item(self.home_score)
        self.add_item(self.away_score)
        self.add_item(self.red_card_given)

    async def on_submit(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('This score form belongs to another user.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            home_score = _parse_score(self.home_score.value, self.fixture['home_team'])
            away_score = _parse_score(self.away_score.value, self.fixture['away_team'])
            message = await _update_score_and_award(
                interaction,
                self.fixture['id'],
                home_score,
                away_score,
                self.tournament_service,
                self.admin_score_update_service,
                red_card_given=self.red_card_given.value.strip() or None,
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        next_index = self.index + 1
        if next_index < len(self.fixtures):
            view = FinalScoreNextView(
                self.tournament_service,
                self.admin_score_update_service,
                self.owner_id,
                self.fixtures,
                next_index,
            )
            await interaction.followup.send(
                (
                    f'{message}\n'
                    f'Updated fixture {self.index + 1} of {len(self.fixtures)}.\n'
                    f'Click the button to open fixture {next_index + 1} of {len(self.fixtures)}.'
                ),
                view=view,
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f'{message}\nUpdated fixture {self.index + 1} of {len(self.fixtures)}.',
            ephemeral=True,
        )


class FinalScoreNextView(discord.ui.View):
    def __init__(self, tournament_service, admin_score_update_service, owner_id, fixtures, index):
        super().__init__(timeout=300)
        self.tournament_service = tournament_service
        self.admin_score_update_service = admin_score_update_service
        self.owner_id = owner_id
        self.fixtures = fixtures
        self.index = index
        self.next_fixture.label = 'Open score form' if index == 0 else 'Open next fixture'

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('Only the command user can use this button.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Next fixture', style=discord.ButtonStyle.primary)
    async def next_fixture(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            FinalScoreModal(
                self.fixtures[self.index],
                self.tournament_service,
                self.admin_score_update_service,
                self.owner_id,
                self.fixtures,
                self.index,
            )
        )


def register_admin_commands(bot, settings):
    announcement_service = AnnouncementService()
    admin_score_update_service = AdminScoreUpdateService()
    tournament_service = TournamentService()

    @bot.tree.command(name='upsert_rules', description='Create or update scoring rules')
    @app_commands.describe(
        name='Optional ruleset name. Defaults to default',
        config_json='Optional ruleset JSON config. Defaults to standard config',
    )
    async def upsert_rules(
        interaction: discord.Interaction,
        name: str | None = None,
        config_json: str | None = None,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        try:
            message = tournament_service.upsert_ruleset(
                {
                    'name': name,
                    'config_json': config_json,
                }
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.response.send_message(message, ephemeral=True)
        await _push_admin_log(interaction, f'{message}\nLog channel: {ADMIN_LOG_CHANNEL_URL}')

    @bot.tree.command(name='upsert_announcement', description='Create or update a scheduled announcement')
    @app_commands.describe(
        announcement_type='Announcement type',
        trigger_gap='Trigger gap in minutes',
    )
    async def upsert_announcement(
        interaction: discord.Interaction,
        announcement_type: Literal['fixture_announcement_2_days'],
        trigger_gap: app_commands.Range[int, 1],
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        try:
            message = announcement_service.upsert_announcement(
                {
                    'announcement_type': announcement_type,
                    'trigger_gap': trigger_gap,
                }
            )
        except ValueError as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.response.send_message(message, ephemeral=True)
        await _push_admin_log(interaction, message)

    @bot.tree.command(name='announcement_status', description='Show scheduled announcement status')
    async def announcement_status(interaction: discord.Interaction):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        rows = announcement_service.status_rows()
        if not rows:
            await interaction.response.send_message('No announcements configured.', ephemeral=True)
            return

        lines = []
        for row in rows:
            lines.append(
                f'{row["announcement_type"]}\n'
                f'Gap: {row["trigger_gap"]} minutes\n'
                f'Last triggered: {_format_datetime(row["last_triggered"])}\n'
                f'Next trigger: {_format_datetime(row["next_trigger_at"])}\n'
                f'Due now: {str(row["due"]).lower()}'
            )
        await interaction.response.send_message('\n\n'.join(lines), ephemeral=True)

    @bot.tree.command(name='run_announcement_now', description='Run a scheduled announcement immediately')
    @app_commands.describe(announcement_type='Announcement type')
    async def run_announcement_now_command(
        interaction: discord.Interaction,
        announcement_type: Literal['fixture_announcement_2_days'],
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            message = await run_announcement_now(interaction.client, settings, announcement_type)
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await _push_admin_log(interaction, message)
        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name='announce_release_notes', description='Post current release notes')
    async def announce_release_notes(interaction: discord.Interaction):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        release_notes = RELEASE_NOTES.get(APP_VERSION)
        if not release_notes:
            await interaction.response.send_message('No release notes found for current version.', ephemeral=True)
            return

        message = '@everyone Bot updates\n' + '\n'.join(f'- {note}' for note in release_notes)
        await push_channel_log(interaction.client, settings.bot_announcement_channel_id, message)
        await interaction.response.send_message('Posted release notes.', ephemeral=True)
        await _push_admin_log(interaction, 'Posted release notes.')

    @bot.tree.command(name='add_tournament', description='Create tournament')
    @app_commands.describe(
        name='Tournament name',
        code='Unique tournament code',
        ruleset_name='Optional ruleset name',
        ruleset_config_json='Optional JSON ruleset config',
    )
    async def add_tournament(
        interaction: discord.Interaction,
        name: str,
        code: str,
        ruleset_name: str | None = None,
        ruleset_config_json: str | None = None,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        try:
            message = tournament_service.add_tournament(
                {
                    'name': name,
                    'code': code,
                    'ruleset_name': ruleset_name,
                    'ruleset_config_json': ruleset_config_json,
                }
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.response.send_message(message, ephemeral=True)
        await _push_admin_log(interaction, message)

    @bot.tree.command(name='update_fixture', description='Create or update fixture')
    @app_commands.describe(
        tournament_code='Tournament code',
        home_team='Home team',
        away_team='Away team',
        kickoff_at='Kickoff time in ISO format',
    )
    @app_commands.autocomplete(tournament_code=_active_tournament_autocomplete)
    async def update_fixture(
        interaction: discord.Interaction,
        tournament_code: str,
        home_team: str,
        away_team: str,
        kickoff_at: str,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        try:
            message = tournament_service.upsert_fixture(
                {
                    'tournament_code': tournament_code,
                    'home_team': home_team,
                    'away_team': away_team,
                    'kickoff_at': kickoff_at,
                }
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.response.send_message(message, ephemeral=True)
        await _push_admin_log(interaction, message)

    @bot.tree.command(name='close_tournament', description='Close an active tournament')
    @app_commands.describe(tournament_code='Tournament code to close')
    @app_commands.autocomplete(tournament_code=_active_tournament_autocomplete)
    async def close_tournament(interaction: discord.Interaction, tournament_code: str):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        try:
            message = tournament_service.close_tournament(tournament_code)
        except LookupError as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.response.send_message(message, ephemeral=True)
        await _push_admin_log(interaction, message)

    @bot.tree.command(name='import_fixtures', description='Import bundled fixtures into a tournament')
    @app_commands.describe(
        tournament_code='Tournament code to import fixtures into',
        filename='Fixture JSON filename inside fixtures directory, without .json',
    )
    @app_commands.autocomplete(tournament_code=_active_tournament_autocomplete)
    async def import_fixtures(
        interaction: discord.Interaction,
        tournament_code: str,
        filename: str,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            message = tournament_service.import_fixtures(tournament_code, filename)
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.followup.send(message, ephemeral=True)
        await _push_admin_log(interaction, message)

    @bot.tree.command(name='update_score', description='Update final score and award score prediction points')
    @app_commands.describe(
        fixture_id='Fixture id',
        home_score='Final home team score',
        away_score='Final away team score',
        red_card_given='Optional actual red-card outcome: yes/no',
    )
    async def update_score(
        interaction: discord.Interaction,
        fixture_id: int,
        home_score: int,
        away_score: int,
        red_card_given: str | None = None,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            message = await _update_score_and_award(
                interaction,
                fixture_id,
                home_score,
                away_score,
                tournament_service,
                admin_score_update_service,
                red_card_given=red_card_given,
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name='update_score_form', description='Update final scores using team-labelled fields')
    @app_commands.describe(
        fixture_id='Single fixture id to update',
        tournament_code='Tournament code for batch mode',
        count='Number of fixtures to update in batch mode',
        start_fixture_id='Optional fixture id to start batch mode from',
    )
    @app_commands.autocomplete(tournament_code=_active_tournament_autocomplete)
    async def update_score_form(
        interaction: discord.Interaction,
        fixture_id: int | None = None,
        tournament_code: str | None = None,
        count: app_commands.Range[int, 1, 5] = 1,
        start_fixture_id: int | None = None,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        if fixture_id is not None and (tournament_code is not None or start_fixture_id is not None or count != 1):
            await interaction.response.send_message(
                'Use either fixture_id for a single score update, or tournament_code/count/start_fixture_id for batch mode.',
                ephemeral=True,
            )
            return

        if fixture_id is None and tournament_code is None:
            await interaction.response.send_message(
                'Provide fixture_id for one fixture, or tournament_code for batch mode.',
                ephemeral=True,
            )
            return

        try:
            if fixture_id is not None:
                fixtures = [tournament_service.get_fixture_details(fixture_id)]
            else:
                fixtures = tournament_service.get_score_form_fixtures(
                    tournament_code,
                    count,
                    start_fixture_id=start_fixture_id,
                )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        if not fixtures:
            await interaction.response.send_message('No fixtures available for score update.', ephemeral=True)
            return

        if len(fixtures) < count:
            await interaction.response.send_message(
                (
                    f'Only {len(fixtures)} fixture(s) are available for score update. '
                    f'Click the button to open fixture 1 of {len(fixtures)}. '
                    'Each submitted form updates the score and recomputes points immediately.'
                ),
                view=FinalScoreNextView(
                    tournament_service,
                    admin_score_update_service,
                    interaction.user.id,
                    fixtures,
                    0,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            FinalScoreModal(
                fixtures[0],
                tournament_service,
                admin_score_update_service,
                interaction.user.id,
                fixtures,
                0,
            )
        )

    @bot.tree.command(name='recompute_points', description='Recompute score and event points for a fixture')
    @app_commands.describe(fixture_id='Fixture id to recompute')
    async def recompute_points(interaction: discord.Interaction, fixture_id: int):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            score_result = admin_score_update_service.award_score_predictions_for_fixture(fixture_id)
            score_message = score_result['message']
            event_result = admin_score_update_service.award_event_predictions_for_fixture(fixture_id)
            event_message = event_result['message']
            leaderboard_message = admin_score_update_service.refresh_leaderboard_for_fixture(fixture_id)
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await _push_admin_log(
            interaction,
            f'Recomputed points for fixture #{fixture_id}.\n'
            f'{score_message}\n'
            f'{event_message}\n'
            f'{leaderboard_message}',
        )
        await _push_prediction_awards(
            interaction,
            fixture_id,
            'score',
            score_result['awarded_users'],
        )
        await _push_prediction_awards(
            interaction,
            fixture_id,
            'event',
            event_result['awarded_users'],
        )
        await _push_prediction_point_losses(
            interaction,
            fixture_id,
            'event',
            event_result.get('removed_users', []),
        )
        await interaction.followup.send(
            f'Recomputed points for fixture #{fixture_id}. '
            f'{score_message} {event_message} {leaderboard_message}',
            ephemeral=True,
        )

    @bot.tree.command(name='revert_score', description='Revert a fixture score and its awarded points')
    @app_commands.describe(fixture_id='Fixture id to revert')
    async def revert_score(interaction: discord.Interaction, fixture_id: int):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            revert_result = admin_score_update_service.revert_score_for_fixture(fixture_id)
            leaderboard_message = admin_score_update_service.refresh_leaderboard_for_fixture(fixture_id)
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await _push_admin_log(
            interaction,
            f'{revert_result["message"]}\n{leaderboard_message}',
        )
        await _push_prediction_removals(
            interaction,
            fixture_id,
            'score',
            revert_result['removed_users'],
        )
        await interaction.followup.send(
            f'{revert_result["message"]} {leaderboard_message}',
            ephemeral=True,
        )

    @bot.tree.command(name='revert_event', description='Revert fixture events and their awarded points')
    @app_commands.describe(
        fixture_id='Fixture id containing the events',
        event_type='Actual event type to remove',
    )
    async def revert_event(
        interaction: discord.Interaction,
        fixture_id: int,
        event_type: Literal['goal', 'red_card'],
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            revert_result = admin_score_update_service.revert_events_for_fixture(
                fixture_id,
                event_type,
            )
            event_result = admin_score_update_service.award_event_predictions_for_fixture(fixture_id)
            leaderboard_message = admin_score_update_service.refresh_leaderboard_for_fixture(fixture_id)
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await _push_admin_log(
            interaction,
            f'{revert_result["message"]}\n'
            f'{event_result["message"]}\n'
            f'{leaderboard_message}',
        )
        await _push_prediction_removals(
            interaction,
            fixture_id,
            'event',
            revert_result['removed_users'],
        )
        await _push_prediction_awards(
            interaction,
            fixture_id,
            'event',
            event_result['awarded_users'],
        )
        await _push_prediction_point_losses(
            interaction,
            fixture_id,
            'event',
            event_result.get('removed_users', []),
        )
        await interaction.followup.send(
            f'{revert_result["message"]} '
            f'{event_result["message"]} '
            f'{leaderboard_message}',
            ephemeral=True,
        )

    @bot.tree.command(name='update_event', description='Create or update goals and red cards')
    @app_commands.describe(
        fixture_id='Fixture id',
        event_type='Actual event type',
        player_name='Player involved in the event',
        team_name='Team for the event',
    )
    async def update_event(
        interaction: discord.Interaction,
        fixture_id: int,
        event_type: Literal['goal', 'red_card'],
        player_name: str,
        team_name: str,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            event_message = tournament_service.upsert_fixture_event(
                {
                    'fixture_id': fixture_id,
                    'event_type': event_type,
                    'player_name': player_name,
                    'team_name': team_name,
                }
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await _push_admin_log(interaction, event_message)
        award_result = admin_score_update_service.award_event_predictions_for_fixture(fixture_id)
        score_message = award_result['message']
        await _push_admin_log(interaction, score_message)
        await _push_prediction_awards(
            interaction,
            fixture_id,
            'event',
            award_result['awarded_users'],
        )
        await _push_prediction_point_losses(
            interaction,
            fixture_id,
            'event',
            award_result.get('removed_users', []),
        )
        leaderboard_message = admin_score_update_service.refresh_leaderboard_for_fixture(fixture_id)
        await _push_admin_log(interaction, leaderboard_message)
        await interaction.followup.send(f'{event_message} {score_message} {leaderboard_message}', ephemeral=True)

    admin_permissions = discord.Permissions(administrator=True)
    for command in bot.tree.get_commands():
        if command.name in ADMIN_COMMAND_NAMES:
            command.default_permissions = admin_permissions
