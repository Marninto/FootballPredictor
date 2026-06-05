from sqlalchemy import func, select

from db.database import db_transaction
from db.models import EventPrediction, Fixture, LeaderboardEntry, ScorePrediction


class AdminScoreUpdateService:
    @db_transaction
    def award_score_predictions_for_fixture(self, fixture_id, db):
        fixture = Fixture.get_by_id(db, fixture_id)
        if fixture.home_score is None or fixture.away_score is None:
            raise ValueError(f'Fixture {fixture_id} does not have a final score yet.')

        rules = fixture.tournament.ruleset.config_json.get('score_prediction', {})
        updated_count = 0
        for prediction in ScorePrediction.find_by_fixture(db, fixture.id):
            points, reason = self._score_prediction_points(prediction, fixture, rules)
            ScorePrediction.award_points(prediction, points, reason)
            updated_count += 1

        db.flush()
        return f'Awarded score prediction points for {updated_count} predictions.'

    @db_transaction
    def award_event_predictions_for_fixture(self, fixture_id, db):
        fixture = Fixture.get_by_id(db, fixture_id)
        rules = fixture.tournament.ruleset.config_json.get('event_prediction', {})
        actual_events = {
            (
                self._prediction_event_type(event.event_type),
                event.player_name.strip().casefold(),
            )
            for event in fixture.fixture_events
        }

        updated_count = 0
        for prediction in EventPrediction.find_by_fixture(db, fixture.id):
            event_key = (
                prediction.event_type.strip(),
                prediction.player_name.strip().casefold(),
            )
            if event_key in actual_events:
                points = int(rules.get(prediction.event_type, 0))
                EventPrediction.award_points(prediction, points, prediction.event_type)
            else:
                EventPrediction.award_points(prediction, 0, 'no_match')
            updated_count += 1

        db.flush()
        return f'Awarded event prediction points for {updated_count} predictions.'

    @db_transaction
    def refresh_leaderboard_for_fixture(self, fixture_id, db):
        fixture = Fixture.get_by_id(db, fixture_id)
        user_ids = self._prediction_user_ids_for_tournament(db, fixture.tournament_id)
        for user_id in user_ids:
            score_points = self._score_points_for_tournament_user(db, fixture.tournament_id, user_id)
            event_points = self._event_points_for_tournament_user(db, fixture.tournament_id, user_id)
            tournament_entry, _ = LeaderboardEntry.get_or_create(db, fixture.tournament_id, user_id)
            LeaderboardEntry.apply_points(tournament_entry, score_points, event_points)

            overall_score_points = self._score_points_for_tournament_user(db, None, user_id)
            overall_event_points = self._event_points_for_tournament_user(db, None, user_id)
            overall_entry, _ = LeaderboardEntry.get_or_create(db, None, user_id)
            LeaderboardEntry.apply_points(overall_entry, overall_score_points, overall_event_points)

        db.flush()
        return f'Refreshed leaderboard entries for {len(user_ids)} users.'

    def _score_prediction_points(self, prediction, fixture, rules):
        if (
            prediction.predicted_home_score == fixture.home_score
            and prediction.predicted_away_score == fixture.away_score
        ):
            return int(rules.get('exact_score', 0)), 'exact_score'

        predicted_difference = prediction.predicted_home_score - prediction.predicted_away_score
        actual_difference = fixture.home_score - fixture.away_score
        if predicted_difference == actual_difference:
            return int(rules.get('correct_goal_difference', 0)), 'correct_goal_difference'
        if self._result_bucket(predicted_difference) == self._result_bucket(actual_difference):
            return int(rules.get('correct_result', 0)), 'correct_result'
        return 0, 'no_match'

    def _prediction_user_ids_for_tournament(self, db, tournament_id):
        score_user_ids = select(ScorePrediction.user_id).join(Fixture).where(Fixture.tournament_id == tournament_id)
        event_user_ids = select(EventPrediction.user_id).join(Fixture).where(Fixture.tournament_id == tournament_id)
        return sorted({row[0] for row in db.execute(score_user_ids.union(event_user_ids)).all()})

    def _score_points_for_tournament_user(self, db, tournament_id, user_id):
        statement = select(func.coalesce(func.sum(ScorePrediction.points_awarded), 0)).join(Fixture).where(
            ScorePrediction.user_id == user_id,
        )
        if tournament_id is not None:
            statement = statement.where(Fixture.tournament_id == tournament_id)
        return int(db.scalar(statement))

    def _event_points_for_tournament_user(self, db, tournament_id, user_id):
        statement = select(func.coalesce(func.sum(EventPrediction.points_awarded), 0)).join(Fixture).where(
            EventPrediction.user_id == user_id,
        )
        if tournament_id is not None:
            statement = statement.where(Fixture.tournament_id == tournament_id)
        return int(db.scalar(statement))

    def _prediction_event_type(self, event_type):
        if event_type == 'goal':
            return 'goalscorer'
        return event_type

    def _result_bucket(self, difference):
        if difference > 0:
            return 'home_win'
        if difference < 0:
            return 'away_win'
        return 'draw'
