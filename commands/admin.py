from typing import Literal

import discord
from discord import app_commands

from services.leaderboard_service import LeaderboardService
from services.scoring_service import ScoringService
from services.tournament_service import TournamentService


def _is_admin(interaction, settings):
    return interaction.user.id in settings.admin_user_ids


async def _deny_admin(interaction):
    await interaction.response.send_message('You do not have permission to use this command.', ephemeral=True)


def register_admin_commands(bot, settings):
    leaderboard_service = LeaderboardService()
    scoring_service = ScoringService()
    tournament_service = TournamentService()

    @bot.tree.command(name='add_tournament', description='Create tournament')
    @app_commands.describe(
        name='Tournament name',
        code='Unique tournament code',
        ruleset_name='Optional ruleset name',
    )
    async def add_tournament(
        interaction: discord.Interaction,
        name: str,
        code: str,
        ruleset_name: str | None = None,
    ):
        if not _is_admin(interaction, settings):
            await _deny_admin(interaction)
            return

        message = tournament_service.add_tournament(name, code, ruleset_name)
        await interaction.response.send_message(message, ephemeral=True)

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

        await interaction.response.send_message(
            f'Fixture upsert is not implemented yet: {tournament_code} {home_team} vs {away_team} at {kickoff_at}.',
            ephemeral=True,
        )

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

        scoring_message = scoring_service.award_score_prediction_points(fixture_id)
        leaderboard_message = leaderboard_service.refresh_for_fixture(fixture_id)
        await interaction.response.send_message(
            f'Final score skeleton updated for fixture {fixture_id}: {home_score}-{away_score}. {scoring_message} {leaderboard_message}',
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

        scoring_message = scoring_service.award_event_prediction_points(fixture_id)
        leaderboard_message = leaderboard_service.refresh_for_fixture(fixture_id)
        await interaction.response.send_message(
            f'Event skeleton updated for fixture {fixture_id}: {event_type} by {player_name} ({team_name}). {scoring_message} {leaderboard_message}',
            ephemeral=True,
        )
