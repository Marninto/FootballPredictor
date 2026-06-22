from sqlalchemy import func, select

from db.database import db_transaction
from db.models import EventPrediction, Fixture, FixtureEvent, LeaderboardEntry, ScorePrediction


class AdminScoreUpdateService:
    @db_transaction
    def revert_score_for_fixture(self, fixture_id, db):
        fixture = Fixture.get_by_id(db, fixture_id)
        if fixture.home_score is None and fixture.away_score is None:
            raise ValueError(f'Fixture {fixture_id} does not have a score to revert.')

        removed_users = {}
        predictions = ScorePrediction.find_by_fixture(db, fixture.id)
        for prediction in predictions:
            if prediction.points_awarded > 0:
                self._record_award(removed_users, prediction.user, prediction.points_awarded)
            ScorePrediction.reset_points(prediction)

        Fixture.revert_score(fixture)
        db.flush()
        return {
            'message': (
                f'Reverted score for fixture #{fixture.id} and reset '
                f'{len(predictions)} score predictions.'
            ),
            'removed_users': self._awarded_user_items(removed_users),
        }

    @db_transaction
    def revert_events_for_fixture(self, fixture_id, event_type, db):
        fixture = Fixture.get_by_id(db, fixture_id)
        prediction_event_type = self._prediction_event_type(event_type)
        removed_users = {}
        for prediction in EventPrediction.find_by_fixture(db, fixture.id):
            if prediction.event_type == prediction_event_type and prediction.points_awarded > 0:
                self._record_award(removed_users, prediction.user, prediction.points_awarded)

        deleted_count = FixtureEvent.delete_by_fixture_and_type(db, fixture.id, event_type)
        if deleted_count == 0:
            raise ValueError(
                f'Fixture {fixture_id} does not have any {event_type} events to revert.'
            )

        db.flush()
        return {
            'message': (
                f'Reverted {deleted_count} {event_type} event(s) for fixture #{fixture.id}.'
            ),
            'removed_users': self._awarded_user_items(removed_users),
        }

    @db_transaction
    def award_score_predictions_for_fixture(self, fixture_id, db):
        fixture = Fixture.get_by_id(db, fixture_id)
        if fixture.home_score is None or fixture.away_score is None:
            raise ValueError(f'Fixture {fixture_id} does not have a final score yet.')

        rules = fixture.tournament.ruleset.config_json.get('score_prediction', {})
        updated_count = 0
        awarded_users = {}
        for prediction in ScorePrediction.find_by_fixture(db, fixture.id):
            points, reason = self._score_prediction_points(prediction, fixture, rules)
            ScorePrediction.award_points(prediction, points, reason)
            if points > 0:
                self._record_award(awarded_users, prediction.user, points)
            updated_count += 1

        db.flush()
        return {
            'message': f'Awarded score prediction points for {updated_count} predictions.',
            'awarded_users': self._awarded_user_items(awarded_users),
        }

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
        red_card_was_given = self._red_card_was_given(fixture)

        updated_count = 0
        awarded_users = {}
        removed_users = {}
        for prediction in EventPrediction.find_by_fixture(db, fixture.id):
            if prediction.event_type == 'red_card_given':
                points, reason = self._red_card_given_points(prediction, fixture, red_card_was_given, rules)
                EventPrediction.award_points(prediction, points, reason)
                if points > 0:
                    self._record_award(awarded_users, prediction.user, points)
                elif points < 0:
                    self._record_award(removed_users, prediction.user, points)
                updated_count += 1
                continue

            event_key = (
                prediction.event_type.strip(),
                prediction.player_name.strip().casefold(),
            )
            if event_key in actual_events:
                points = int(rules.get(prediction.event_type, 0))
                EventPrediction.award_points(prediction, points, prediction.event_type)
                if points > 0:
                    self._record_award(awarded_users, prediction.user, points)
            else:
                EventPrediction.award_points(prediction, 0, 'no_match')
            updated_count += 1

        db.flush()
        return {
            'message': f'Awarded event prediction points for {updated_count} predictions.',
            'awarded_users': self._awarded_user_items(awarded_users),
            'removed_users': self._awarded_user_items(removed_users),
        }

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
        reasons = []
        points = 0
        if self._result_bucket(predicted_difference) == self._result_bucket(actual_difference):
            points += int(rules.get('correct_result', 0))
            reasons.append('correct_result')
        if predicted_difference == actual_difference:
            points += int(rules.get('correct_goal_difference', 0))
            reasons.append('correct_goal_difference')
        if reasons:
            return points, '+'.join(reasons)
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

    def _red_card_given_points(self, prediction, fixture, red_card_was_given, rules):
        if 'red_card_given' not in rules:
            return 0, 'disabled'
        if fixture.home_score is None or fixture.away_score is None:
            return 0, 'pending_final_score'
        red_card_rules = rules.get('red_card_given', {})
        predicted_red_card = prediction.player_name.strip().casefold() == 'true'
        if predicted_red_card and red_card_was_given:
            return int(red_card_rules.get('yes_correct', 0)), 'red_card_given_yes_correct'
        if predicted_red_card and not red_card_was_given:
            return int(red_card_rules.get('yes_incorrect', 0)), 'red_card_given_yes_incorrect'
        if not predicted_red_card and not red_card_was_given:
            return int(red_card_rules.get('no_correct', 0)), 'red_card_given_no_correct'
        return int(red_card_rules.get('no_incorrect', 0)), 'red_card_given_no_incorrect'

    def _red_card_was_given(self, fixture):
        red_card_given_events = [
            event for event in fixture.fixture_events if event.event_type == 'red_card_given'
        ]
        if red_card_given_events:
            return red_card_given_events[-1].player_name.strip().casefold() == 'true'
        return any(event.event_type == 'red_card' for event in fixture.fixture_events)

    def _awarded_user_items(self, awarded_users):
        return [
            {
                'discord_user_id': discord_user_id,
                **award,
            }
            for discord_user_id, award in awarded_users.items()
        ]

    def _record_award(self, awarded_users, user, points):
        award = awarded_users.setdefault(
            user.discord_user_id,
            {
                'display_name': user.discord_display_name,
                'points': 0,
            },
        )
        award['points'] += points

    def _result_bucket(self, difference):
        if difference > 0:
            return 'home_win'
        if difference < 0:
            return 'away_win'
        return 'draw'
