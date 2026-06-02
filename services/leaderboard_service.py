class LeaderboardService:
    def show_leaderboard(self, tournament_code=None):
        if tournament_code:
            return f'Leaderboard for {tournament_code} is not implemented yet.'
        return 'Overall leaderboard is not implemented yet.'

    def show_points(self, user_id, target_user_id=None):
        selected_user_id = target_user_id or user_id
        return f'Points summary is not implemented yet for user {selected_user_id}.'

    def refresh_for_fixture(self, fixture_id):
        return f'Leaderboard refresh is not implemented yet for fixture {fixture_id}.'
