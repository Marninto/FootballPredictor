from typing import Literal

import discord
from discord import app_commands

from config.constants import ADMIN_LOG_CHANNEL_URL
from services.admin_score_update_service import AdminScoreUpdateService
from services.tournament_service import TournamentService
from utils.discord_logs import log_error, push_admin_log, push_prediction_award_log


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


async def _push_prediction_awards(interaction, fixture_id, awarded_users):
    if not awarded_users:
        return
    mentions = ', '.join(f'<@{user["discord_user_id"]}>' for user in awarded_users)
    await push_prediction_award_log(
        interaction.client,
        f'Fixture #{fixture_id} event prediction points awarded to: {mentions}',
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
):
    fixture_message = tournament_service.update_fixture_score(
        {
            'fixture_id': fixture_id,
            'home_score': home_score,
            'away_score': away_score,
        }
    )
    await _push_admin_log(interaction, fixture_message)
    score_message = admin_score_update_service.award_score_predictions_for_fixture(fixture_id)
    await _push_admin_log(interaction, score_message)
    leaderboard_message = admin_score_update_service.refresh_leaderboard_for_fixture(fixture_id)
    await _push_admin_log(interaction, leaderboard_message)
    return f'{fixture_message} {score_message} {leaderboard_message}'


class FinalScoreModal(discord.ui.Modal):
    def __init__(self, fixture, tournament_service, admin_score_update_service, owner_id):
        super().__init__(title=f'Update fixture #{fixture["id"]}')
        self.fixture = fixture
        self.tournament_service = tournament_service
        self.admin_score_update_service = admin_score_update_service
        self.owner_id = owner_id
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
        self.add_item(self.home_score)
        self.add_item(self.away_score)

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
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return
        await interaction.followup.send(message, ephemeral=True)


def register_admin_commands(bot, settings):
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

    @bot.tree.command(name='update_score', description='Update final score and award score prediction points')
    @app_commands.describe(
        fixture_id='Fixture id',
        home_score='Final home team score',
        away_score='Final away team score',
    )
    async def update_score(interaction: discord.Interaction, fixture_id: int, home_score: int, away_score: int):
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
            )
        except (ValueError, LookupError) as error:
            await _send_admin_error(interaction, error)
            return

        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name='update_score_form', description='Update a final score using team-labelled fields')
    @app_commands.describe(fixture_id='Fixture id')
    async def update_score_form(interaction: discord.Interaction, fixture_id: int):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return
        try:
            fixture = tournament_service.get_fixture_details(fixture_id)
        except LookupError as error:
            await _send_admin_error(interaction, error)
            return
        await interaction.response.send_modal(
            FinalScoreModal(
                fixture,
                tournament_service,
                admin_score_update_service,
                interaction.user.id,
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
            score_message = admin_score_update_service.award_score_predictions_for_fixture(fixture_id)
            award_result = admin_score_update_service.award_event_predictions_for_fixture(fixture_id)
            event_message = award_result['message']
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
        await _push_prediction_awards(interaction, fixture_id, award_result['awarded_users'])
        await interaction.followup.send(
            f'Recomputed points for fixture #{fixture_id}. '
            f'{score_message} {event_message} {leaderboard_message}',
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
        await _push_prediction_awards(interaction, fixture_id, award_result['awarded_users'])
        leaderboard_message = admin_score_update_service.refresh_leaderboard_for_fixture(fixture_id)
        await _push_admin_log(interaction, leaderboard_message)
        await interaction.followup.send(f'{event_message} {score_message} {leaderboard_message}', ephemeral=True)
