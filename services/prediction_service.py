from db.database import db_transaction
from db.models import EventPrediction, Fixture, ScorePrediction, User
from utils.validation import validate_fixture_open_for_prediction, validate_player_name


class PredictionService:
    @db_transaction
    def predict_score(self, discord_user, fixture_id, home_score, away_score, db=None):
        fixture = Fixture.get_by_id(db, fixture_id)
        validate_fixture_open_for_prediction(fixture)
        user, _ = User.get_or_create_from_discord(db, discord_user.id, discord_user.display_name)
        prediction, created = ScorePrediction.upsert_from_dict(
            db,
            {
                'user_id': user.id,
                'fixture_id': fixture.id,
                'predicted_home_score': home_score,
                'predicted_away_score': away_score,
            },
        )
        action = 'Created' if created else 'Updated'
        return f'{action} score prediction for {fixture.home_team} vs {fixture.away_team}: {prediction.predicted_home_score}-{prediction.predicted_away_score}.'

    @db_transaction
    def predict_event(self, discord_user, fixture_id, event_type, player_name, db=None):
        fixture = Fixture.get_by_id(db, fixture_id)
        validate_fixture_open_for_prediction(fixture)
        player_name = validate_player_name(player_name)
        user, _ = User.get_or_create_from_discord(db, discord_user.id, discord_user.display_name)
        prediction, created = EventPrediction.upsert_from_dict(
            db,
            {
                'user_id': user.id,
                'fixture_id': fixture.id,
                'event_type': event_type,
                'player_name': player_name,
            },
        )
        action = 'Created' if created else 'Updated'
        return f'{action} {prediction.event_type} prediction for {fixture.home_team} vs {fixture.away_team}: {prediction.player_name}.'

    def list_predictions(self, user_id, target_user_id=None, tournament_code=None, page=1):
        selected_user_id = target_user_id or user_id
        suffix = f' for tournament {tournament_code}' if tournament_code else ''
        return f'Prediction listing is not implemented yet for user {selected_user_id}{suffix}, page {page}.'
