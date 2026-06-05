from db.database import db_transaction
from db.models import LeaderboardEntry, User


class UserService:
    @db_transaction
    def get_profile(self, requester, target=None, db=None):
        selected = target or requester
        user = User.find_by_discord_user_id(db, selected.id)
        if user is None:
            return {
                'display_name': selected.display_name,
                'total_points': None,
                'global_rank': None,
                'tournament_rank': None,
                'event_points': None,
                'prediction_points': None,
                'global_event_rank': None,
                'tournament_event_rank': None,
            }

        global_entry = LeaderboardEntry.global_entry_for_user(db, user.id)
        tournament_entry = LeaderboardEntry.best_tournament_entry_for_user(db, user.id)
        return {
            'display_name': user.discord_display_name,
            'total_points': self._positive_or_none(global_entry.total_points if global_entry else None),
            'global_rank': LeaderboardEntry.rank_for_total_points(db, global_entry),
            'tournament_rank': LeaderboardEntry.rank_for_total_points(db, tournament_entry),
            'event_points': self._positive_or_none(global_entry.event_prediction_points if global_entry else None),
            'prediction_points': self._positive_or_none(global_entry.score_prediction_points if global_entry else None),
            'global_event_rank': LeaderboardEntry.rank_for_event_points(db, global_entry),
            'tournament_event_rank': LeaderboardEntry.rank_for_event_points(db, tournament_entry),
        }

    @db_transaction
    def set_prediction_visibility(self, discord_user_id, display_name, visibility, db=None):
        user, _ = User.get_or_create_from_discord(db, discord_user_id, display_name)
        User.set_prediction_visibility(user, visibility)
        db.flush()
        return f'Prediction visibility set to {visibility}.'

    def _positive_or_none(self, value):
        if value is None or value <= 0:
            return None
        return value
