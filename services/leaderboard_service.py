from math import ceil

from db.database import db_transaction
from db.models import LeaderboardEntry, Tournament, User
from db.pagination import paginate_query


class LeaderboardService:
    @db_transaction
    def get_leaderboard(self, tournament_code=None, point_filter='total', page=1, page_size=10, db=None):
        tournament = Tournament.get_by_code(db, tournament_code) if tournament_code else None
        tournament_id = tournament.id if tournament else None
        leaderboard_page = paginate_query(
            db,
            LeaderboardEntry.leaderboard_statement(tournament_id, point_filter),
            page=page,
            page_size=page_size,
        )
        start_rank = (leaderboard_page.page - 1) * leaderboard_page.page_size
        rows = [
            self._entry_row(entry, start_rank + index + 1, point_filter)
            for index, entry in enumerate(leaderboard_page.items)
        ]
        return {
            'page': leaderboard_page,
            'rows': rows,
            'title': f'{tournament.code} Leaderboard' if tournament else 'Global Leaderboard',
            'point_filter': point_filter,
            'tournament_code': tournament.code if tournament else None,
        }

    @db_transaction
    def page_for_user(self, discord_user_id, tournament_code=None, point_filter='total', page_size=10, db=None):
        tournament = Tournament.get_by_code(db, tournament_code) if tournament_code else None
        user = User.find_by_discord_user_id(db, discord_user_id)
        if user is None:
            return 1

        rank = LeaderboardEntry.rank_for_user(db, tournament.id if tournament else None, user.id, point_filter)
        if rank is None:
            return 1
        return max(ceil(rank / page_size), 1)

    def show_points(self, user_id, target_user_id=None):
        selected_user_id = target_user_id or user_id
        return f'Points summary is not implemented yet for user {selected_user_id}.'

    def refresh_for_fixture(self, fixture_id):
        return f'Leaderboard refresh is not implemented yet for fixture {fixture_id}.'

    def _entry_row(self, entry, rank, point_filter):
        selected_points = getattr(entry, LeaderboardEntry.point_column(point_filter).key)
        return {
            'rank': rank,
            'display_name': entry.user.discord_display_name,
            'selected_points': selected_points,
            'total_points': entry.total_points,
            'event_points': entry.event_prediction_points,
            'prediction_points': entry.score_prediction_points,
        }
