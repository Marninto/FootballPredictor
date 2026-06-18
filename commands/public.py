from typing import Literal

import discord
from discord import app_commands

from services.leaderboard_service import LeaderboardService
from services.prediction_service import PredictionService
from services.tournament_service import TournamentService
from services.user_service import UserService
from utils.discord_logs import log_error


def _format_value(value):
    return 'N/A' if value is None else str(value)


def _profile_embed(profile):
    embed = discord.Embed(title=f'{profile["display_name"]} Profile', color=discord.Color.green())
    embed.add_field(name='Total Points', value=_format_value(profile['total_points']), inline=True)
    embed.add_field(name='Global Rank', value=_format_value(profile['global_rank']), inline=True)
    embed.add_field(name='Tournament Rank', value=_format_value(profile['tournament_rank']), inline=True)
    embed.add_field(name='Event Points', value=_format_value(profile['event_points']), inline=True)
    embed.add_field(name='Prediction Points', value=_format_value(profile['prediction_points']), inline=True)
    embed.add_field(name='Global Event Rank', value=_format_value(profile['global_event_rank']), inline=True)
    embed.add_field(name='Tournament Event Rank', value=_format_value(profile['tournament_event_rank']), inline=True)
    return embed


def _rules_embed(ruleset_name, config_json):
    embed = discord.Embed(title=f'{ruleset_name} Rules', color=discord.Color.blue())
    score_rules = config_json.get('score_prediction', {})
    event_rules = config_json.get('event_prediction', {})
    embed.add_field(
        name='Score Prediction',
        value='\n'.join(f'{key}: {value}' for key, value in score_rules.items()) or 'N/A',
        inline=False,
    )
    embed.add_field(
        name='Event Prediction',
        value='\n'.join(f'{key}: {value}' for key, value in event_rules.items()) or 'N/A',
        inline=False,
    )
    return embed


def _tournament_embed(page, items):
    embed = discord.Embed(title='Active Tournaments', color=discord.Color.gold())
    if not items:
        embed.description = 'No active tournaments found.'
    for item in items:
        embed.add_field(
            name=f'{item["code"]} - {item["name"]}',
            value=f'Prediction users: {item["prediction_users"]}',
            inline=False,
        )
    embed.set_footer(text=f'Page {page.page} of {page.total_pages}')
    return embed


def _leaderboard_embed(data):
    page = data['page']
    point_filter = data['point_filter']
    embed = discord.Embed(title=data['title'], color=discord.Color.purple())
    embed.description = f'Filter: {point_filter}'
    if not data['rows']:
        embed.add_field(name='No entries', value='No leaderboard entries found.', inline=False)
    for row in data['rows']:
        embed.add_field(
            name=f'#{row["rank"]} {row["display_name"]}',
            value=(
                f'{point_filter.title()} points: {row["selected_points"]}\n'
                f'Total: {row["total_points"]} | Event: {row["event_points"]} | Prediction: {row["prediction_points"]}'
            ),
            inline=False,
        )
    embed.set_footer(text=f'Page {page.page} of {page.total_pages}')
    return embed


def _fixtures_embed(data):
    page = data['page']
    embed = discord.Embed(
        title=f'{data["tournament_code"]} Fixtures',
        description=f'{data["tournament_name"]} | Filter: {data["fixture_filter"]}',
        color=discord.Color.teal(),
    )
    if not data['items']:
        embed.add_field(name='No fixtures', value='No fixtures matched this filter.', inline=False)
    for item in data['items']:
        predicted_score = (
            f'{item["predicted_home_score"]}-{item["predicted_away_score"]}'
            if item['predicted_home_score'] is not None and item['predicted_away_score'] is not None
            else 'N/A'
        )
        actual_score = (
            f'{item["home_score"]}-{item["away_score"]}'
            if item['home_score'] is not None and item['away_score'] is not None
            else 'X-X'
        )
        predicted_goalscorers = ', '.join(item['predicted_goalscorers']) or 'N/A'
        points_line = (
            f'\nPoints earned: {item["points_earned"]}'
            if item['points_earned'] is not None
            else ''
        )
        embed.add_field(
            name=f'#{item["id"]} | {item["kickoff_at"].strftime("%Y-%m-%d %H:%M UTC")}',
            value=(
                f'{item["home_team"]} {actual_score} {item["away_team"]}\n'
                f'Predicted score: {predicted_score}\n'
                f'Predicted Goalscorer: {predicted_goalscorers}\n'
                f'Predicted: {str(item["predicted"]).lower()}'
                f'{points_line}'
            ),
            inline=False,
        )
    embed.set_footer(text=f'Page {page.page} of {page.total_pages}')
    return embed


async def _send_public_error(interaction, error):
    await log_error(
        interaction.client,
        'Handled public command error',
        error,
        context=f'Command: {interaction.command}\nUser: {interaction.user} ({interaction.user.id})',
    )
    await interaction.response.send_message(str(error), ephemeral=True)


def _parse_score(value, team_name):
    try:
        score = int(value)
    except ValueError as error:
        raise ValueError(f'{team_name} score must be a whole number.') from error
    if score < 0:
        raise ValueError(f'{team_name} score cannot be negative.')
    return score


class ScorePredictionModal(discord.ui.Modal):
    def __init__(self, fixture, prediction_service, owner_id):
        super().__init__(title=f'Predict fixture #{fixture["id"]}')
        self.fixture = fixture
        self.prediction_service = prediction_service
        self.owner_id = owner_id
        self.home_score = discord.ui.TextInput(
            label=f'{fixture["home_team"]} score'[:45],
            placeholder='0',
            min_length=1,
            max_length=2,
        )
        self.away_score = discord.ui.TextInput(
            label=f'{fixture["away_team"]} score'[:45],
            placeholder='0',
            min_length=1,
            max_length=2,
        )
        self.add_item(self.home_score)
        self.add_item(self.away_score)

    async def on_submit(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('This prediction form belongs to another user.', ephemeral=True)
            return
        try:
            home_score = _parse_score(self.home_score.value, self.fixture['home_team'])
            away_score = _parse_score(self.away_score.value, self.fixture['away_team'])
            message = self.prediction_service.predict_score(
                interaction.user,
                self.fixture['id'],
                home_score,
                away_score,
            )
        except (ValueError, LookupError) as error:
            await _send_public_error(interaction, error)
            return
        await interaction.response.send_message(message, ephemeral=True)


class TournamentPaginationView(discord.ui.View):
    def __init__(self, tournament_service, owner_id, page=1):
        super().__init__(timeout=120)
        self.tournament_service = tournament_service
        self.owner_id = owner_id
        self.page = page

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('Only the command user can use these buttons.', ephemeral=True)
            return False
        return True

    async def _render(self, interaction, page):
        tournament_page, items = self.tournament_service.list_active_tournaments(page=page)
        self.page = tournament_page.page
        self.previous_page.disabled = not tournament_page.has_previous
        self.next_page.disabled = not tournament_page.has_next
        await interaction.response.edit_message(embed=_tournament_embed(tournament_page, items), view=self)

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page - 1)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page + 1)


class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, leaderboard_service, user_id, tournament_code=None, point_filter='total', page=1):
        super().__init__(timeout=120)
        self.leaderboard_service = leaderboard_service
        self.user_id = user_id
        self.tournament_code = tournament_code
        self.point_filter = point_filter
        self.page = page

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Only the command user can use these buttons.', ephemeral=True)
            return False
        return True

    async def _render(self, interaction, page):
        data = self.leaderboard_service.get_leaderboard(
            tournament_code=self.tournament_code,
            point_filter=self.point_filter,
            page=page,
        )
        self.page = data['page'].page
        self._set_button_states(data['page'])
        await interaction.response.edit_message(embed=_leaderboard_embed(data), view=self)

    def _set_button_states(self, page):
        self.first_page.disabled = not page.has_previous
        self.previous_page.disabled = not page.has_previous
        self.next_page.disabled = not page.has_next
        self.last_page.disabled = not page.has_next

    @discord.ui.button(label='First', style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, 1)

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page - 1)

    @discord.ui.button(label='User', style=discord.ButtonStyle.primary)
    async def user_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        page = self.leaderboard_service.page_for_user(
            self.user_id,
            tournament_code=self.tournament_code,
            point_filter=self.point_filter,
        )
        await self._render(interaction, page)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page + 1)

    @discord.ui.button(label='Last', style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.leaderboard_service.get_leaderboard(
            tournament_code=self.tournament_code,
            point_filter=self.point_filter,
            page=self.page,
        )
        await self._render(interaction, data['page'].total_pages)


class FixturePaginationView(discord.ui.View):
    def __init__(self, tournament_service, user, tournament_code, fixture_filter='all', page=1):
        super().__init__(timeout=120)
        self.tournament_service = tournament_service
        self.user = user
        self.tournament_code = tournament_code
        self.fixture_filter = fixture_filter
        self.page = page

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message('Only the command user can use these buttons.', ephemeral=True)
            return False
        return True

    async def _render(self, interaction, page):
        data = self.tournament_service.list_fixtures(
            self.user,
            self.tournament_code,
            fixture_filter=self.fixture_filter,
            page=page,
        )
        self.page = data['page'].page
        self._set_button_states(data['page'])
        await interaction.response.edit_message(embed=_fixtures_embed(data), view=self)

    def _set_button_states(self, page):
        self.first_page.disabled = not page.has_previous
        self.previous_page.disabled = not page.has_previous
        self.next_page.disabled = not page.has_next
        self.last_page.disabled = not page.has_next

    @discord.ui.button(label='First', style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, 1)

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page - 1)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page + 1)

    @discord.ui.button(label='Last', style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.tournament_service.list_fixtures(
            self.user,
            self.tournament_code,
            fixture_filter=self.fixture_filter,
            page=self.page,
        )
        await self._render(interaction, data['page'].total_pages)


def register_public_commands(bot):
    leaderboard_service = LeaderboardService()
    prediction_service = PredictionService()
    tournament_service = TournamentService()
    user_service = UserService()

    @bot.tree.command(name='tournament', description='Show active tournaments')
    async def tournament(interaction: discord.Interaction):
        tournament_page, items = tournament_service.list_active_tournaments()
        view = TournamentPaginationView(tournament_service, interaction.user.id, tournament_page.page)
        view.previous_page.disabled = not tournament_page.has_previous
        view.next_page.disabled = not tournament_page.has_next
        await interaction.response.send_message(embed=_tournament_embed(tournament_page, items), view=view)

    @bot.tree.command(name='fixtures', description='Show tournament fixtures')
    @app_commands.describe(
        tournament_code='Tournament code',
        fixture_filter='Fixture filter',
    )
    async def fixtures(
        interaction: discord.Interaction,
        tournament_code: str,
        fixture_filter: Literal['all', 'predicted', 'open'] = 'all',
    ):
        try:
            data = tournament_service.list_fixtures(interaction.user, tournament_code, fixture_filter=fixture_filter)
        except LookupError as error:
            await _send_public_error(interaction, error)
            return

        view = FixturePaginationView(
            tournament_service,
            interaction.user,
            tournament_code,
            fixture_filter=fixture_filter,
            page=data['page'].page,
        )
        view._set_button_states(data['page'])
        await interaction.response.send_message(embed=_fixtures_embed(data), view=view, ephemeral=True)

    @bot.tree.command(name='predict', description='Predict fixture score')
    @app_commands.describe(
        fixture_id='Fixture id to predict',
        home_score='Predicted home team score',
        away_score='Predicted away team score',
    )
    async def predict(interaction: discord.Interaction, fixture_id: int, home_score: int, away_score: int):
        try:
            message = prediction_service.predict_score(interaction.user, fixture_id, home_score, away_score)
        except (ValueError, LookupError) as error:
            await _send_public_error(interaction, error)
            return

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name='predict_score_form', description='Predict a score using team-labelled fields')
    @app_commands.describe(fixture_id='Fixture id to predict')
    async def predict_score_form(interaction: discord.Interaction, fixture_id: int):
        try:
            fixture = prediction_service.get_predictable_fixture_details(fixture_id)
        except (ValueError, LookupError) as error:
            await _send_public_error(interaction, error)
            return
        await interaction.response.send_modal(
            ScorePredictionModal(fixture, prediction_service, interaction.user.id)
        )

    @bot.tree.command(name='predict_event', description='Predict goalscorer or red card')
    @app_commands.describe(
        fixture_id='Fixture id to predict',
        event_type='Event type to predict',
        player_name='Player involved in the predicted event',
    )
    async def predict_event(
        interaction: discord.Interaction,
        fixture_id: int,
        event_type: Literal['goalscorer', 'red_card'],
        player_name: str,
    ):
        try:
            message = prediction_service.predict_event(interaction.user, fixture_id, event_type, player_name)
        except (ValueError, LookupError) as error:
            await _send_public_error(interaction, error)
            return

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name='rules', description='Show tournament scoring rules')
    @app_commands.describe(tournament_code='Optional tournament code')
    async def rules(interaction: discord.Interaction, tournament_code: str | None = None):
        try:
            ruleset_name, config_json = tournament_service.show_rules(tournament_code)
        except LookupError as error:
            await _send_public_error(interaction, error)
            return

        await interaction.response.send_message(embed=_rules_embed(ruleset_name, config_json), ephemeral=True)

    @bot.tree.command(name='leaderboard', description='Show tournament or overall leaderboard')
    @app_commands.describe(
        tournament_code='Optional tournament code',
        point_filter='Leaderboard point filter',
    )
    async def leaderboard(
        interaction: discord.Interaction,
        tournament_code: str | None = None,
        point_filter: Literal['total', 'event', 'prediction'] = 'total',
    ):
        try:
            data = leaderboard_service.get_leaderboard(tournament_code=tournament_code, point_filter=point_filter)
        except LookupError as error:
            await _send_public_error(interaction, error)
            return

        view = LeaderboardPaginationView(
            leaderboard_service,
            interaction.user.id,
            tournament_code=tournament_code,
            point_filter=point_filter,
            page=data['page'].page,
        )
        view._set_button_states(data['page'])
        await interaction.response.send_message(embed=_leaderboard_embed(data), view=view)

    @bot.tree.command(name='profile', description="Show your profile or another user's profile")
    @app_commands.describe(user='Optional user to inspect')
    async def profile(interaction: discord.Interaction, user: discord.User | None = None):
        profile_data = user_service.get_profile(interaction.user, user)
        await interaction.response.send_message(embed=_profile_embed(profile_data))

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

    # @bot.tree.command(name='points', description="Show your points or another user's points summary")
    # @app_commands.describe(user='Optional user to inspect')
    # async def points(interaction: discord.Interaction, user: discord.Member | None = None):
    #     target_user_id = user.id if user else None
    #     message = leaderboard_service.show_points(interaction.user.id, target_user_id)
    #     await interaction.response.send_message(message, ephemeral=user is None)

    @bot.tree.command(name='set_visibility', description='Control prediction visibility')
    @app_commands.describe(visibility='Prediction visibility')
    async def set_visibility(interaction: discord.Interaction, visibility: Literal['public', 'private']):
        message = user_service.set_prediction_visibility(interaction.user.id, interaction.user.display_name, visibility)
        await interaction.response.send_message(message, ephemeral=True)
