from db.database import db_transaction
from db.models import EventPrediction, Fixture, ScorePrediction, Tournament, User
from utils.validation import validate_fixture_open_for_prediction, validate_player_name


class PredictionService:
    @db_transaction
    def prediction_response_ephemeral(self, discord_user, db=None):
        user = User.find_by_discord_user_id(db, discord_user.id)
        if user is None:
            return False
        return user.prediction_visibility != 'public'

    @db_transaction
    def get_predictable_fixture_details(self, fixture_id, db=None):
        fixture = Fixture.get_by_id(db, fixture_id)
        validate_fixture_open_for_prediction(fixture)
        return {
            'id': fixture.id,
            'home_team': fixture.home_team,
            'away_team': fixture.away_team,
        }

    @db_transaction
    def get_predict_form_fixtures(
        self,
        discord_user,
        tournament_code,
        count,
        start_fixture_id=None,
        db=None,
    ):
        count = int(count)
        if count < 1 or count > 5:
            raise ValueError('count must be between 1 and 5.')

        tournament = Tournament.get_by_code(db, tournament_code)
        user, _ = User.get_or_create_from_discord(db, discord_user.id, discord_user.display_name)

        if start_fixture_id is not None:
            start_fixture = Fixture.get_by_id(db, start_fixture_id)
            if start_fixture.tournament_id != tournament.id:
                raise ValueError(f'Fixture {start_fixture_id} is not in tournament {tournament.code}.')
            validate_fixture_open_for_prediction(start_fixture)

        fixtures = db.scalars(
            Fixture.open_statement(
                tournament.id,
                start_fixture_id=start_fixture_id,
            ).limit(count)
        ).all()
        fixture_details = []
        for fixture in fixtures:
            score_prediction = ScorePrediction.find_by_user_and_fixture(db, user.id, fixture.id)
            goalscorer_prediction = EventPrediction.find_by_prediction_key(
                db,
                {
                    'user_id': user.id,
                    'fixture_id': fixture.id,
                    'event_type': 'goalscorer',
                },
            )
            fixture_details.append(
                {
                    'id': fixture.id,
                    'home_team': fixture.home_team,
                    'away_team': fixture.away_team,
                    'predicted_home_score': (
                        score_prediction.predicted_home_score if score_prediction is not None else None
                    ),
                    'predicted_away_score': (
                        score_prediction.predicted_away_score if score_prediction is not None else None
                    ),
                    'predicted_goalscorer': (
                        goalscorer_prediction.player_name if goalscorer_prediction is not None else None
                    ),
                }
            )
        return fixture_details

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
