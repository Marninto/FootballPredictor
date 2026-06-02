from typing import Literal

import discord
from discord import app_commands

from services.leaderboard_service import LeaderboardService
from services.prediction_service import PredictionService
from services.tournament_service import TournamentService
from services.user_service import UserService


def register_public_commands(bot):
    leaderboard_service = LeaderboardService()
    prediction_service = PredictionService()
    tournament_service = TournamentService()
    user_service = UserService()

    @bot.tree.command(name='tournament', description='Show active tournaments')
    async def tournament(interaction: discord.Interaction):
        await interaction.response.send_message(tournament_service.list_active_tournaments())

    @bot.tree.command(name='predict', description='Predict fixture score')
    @app_commands.describe(
        fixture_id='Fixture id to predict',
        home_score='Predicted home team score',
        away_score='Predicted away team score',
    )
    async def predict(interaction: discord.Interaction, fixture_id: int, home_score: int, away_score: int):
        message = prediction_service.predict_score(fixture_id, home_score, away_score)
        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name='predict_event', description='Predict goalscorer or red card')
    @app_commands.describe(
        fixture_id='Fixture id to predict',
        event_type='Event type to predict',
        player_name='Player involved in the predicted event',
        team_name='Team for the predicted event',
    )
    async def predict_event(
        interaction: discord.Interaction,
        fixture_id: int,
        event_type: Literal['goalscorer', 'red_card'],
        player_name: str,
        team_name: str,
    ):
        message = prediction_service.predict_event(fixture_id, event_type, player_name, team_name)
        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name='rules', description='Show tournament scoring rules')
    @app_commands.describe(tournament_code='Optional tournament code')
    async def rules(interaction: discord.Interaction, tournament_code: str | None = None):
        await interaction.response.send_message(tournament_service.show_rules(tournament_code))

    @bot.tree.command(name='leaderboard', description='Show tournament or overall leaderboard')
    @app_commands.describe(tournament_code='Optional tournament code')
    async def leaderboard(interaction: discord.Interaction, tournament_code: str | None = None):
        await interaction.response.send_message(leaderboard_service.show_leaderboard(tournament_code))

    @bot.tree.command(name='profile', description="Show your profile or another user's profile")
    @app_commands.describe(user='Optional user to inspect')
    async def profile(interaction: discord.Interaction, user: discord.Member | None = None):
        target_user_id = user.id if user else None
        message = user_service.show_profile(interaction.user.id, target_user_id)
        await interaction.response.send_message(message)

    @bot.tree.command(name='predictions', description="Show your predictions or another user's public predictions")
    @app_commands.describe(
        user='Optional user to inspect',
        tournament_code='Optional tournament filter',
        page='Page number',
    )
    async def predictions(
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        tournament_code: str | None = None,
        page: app_commands.Range[int, 1] = 1,
    ):
        target_user_id = user.id if user else None
        message = prediction_service.list_predictions(interaction.user.id, target_user_id, tournament_code, page)
        await interaction.response.send_message(message, ephemeral=user is None)

    @bot.tree.command(name='points', description="Show your points or another user's points summary")
    @app_commands.describe(user='Optional user to inspect')
    async def points(interaction: discord.Interaction, user: discord.Member | None = None):
        target_user_id = user.id if user else None
        message = leaderboard_service.show_points(interaction.user.id, target_user_id)
        await interaction.response.send_message(message, ephemeral=user is None)

    @bot.tree.command(name='set_visibility', description='Control prediction visibility')
    @app_commands.describe(visibility='Prediction visibility')
    async def set_visibility(interaction: discord.Interaction, visibility: Literal['public', 'private']):
        message = user_service.set_prediction_visibility(interaction.user.id, visibility)
        await interaction.response.send_message(message, ephemeral=True)
