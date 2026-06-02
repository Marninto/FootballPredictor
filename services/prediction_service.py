class PredictionService:
    def predict_score(self, fixture_id, home_score, away_score):
        return f'Score prediction skeleton saved for fixture {fixture_id}: {home_score}-{away_score}.'

    def predict_event(self, fixture_id, event_type, player_name, team_name):
        return f'Event prediction skeleton saved for fixture {fixture_id}: {event_type} by {player_name} ({team_name}).'

    def list_predictions(self, user_id, target_user_id=None, tournament_code=None, page=1):
        selected_user_id = target_user_id or user_id
        suffix = f' for tournament {tournament_code}' if tournament_code else ''
        return f'Prediction listing is not implemented yet for user {selected_user_id}{suffix}, page {page}.'
