import json

from db.pagination import paginate_query
from db.database import db_transaction
from db.models import EventPrediction, Fixture, FixtureEvent, Ruleset, ScorePrediction, Tournament, User
from domain.scoring_rules import DEFAULT_RULESET_CONFIG, validate_ruleset_config
from utils.boolean_prediction import parse_yes_no


class TournamentService:
    @db_transaction
    def get_fixture_details(self, fixture_id, db=None):
        fixture = Fixture.get_by_id(db, fixture_id)
        return {
            'id': fixture.id,
            'home_team': fixture.home_team,
            'away_team': fixture.away_team,
            'home_score': fixture.home_score,
            'away_score': fixture.away_score,
            'red_card_given': self._actual_red_card_given(fixture),
        }

    @db_transaction
    def get_score_form_fixtures(self, tournament_code, count, start_fixture_id=None, db=None):
        count = int(count)
        if count < 1 or count > 5:
            raise ValueError('count must be between 1 and 5.')

        tournament = Tournament.get_by_code(db, tournament_code)
        start_kickoff_at = None
        if start_fixture_id is not None:
            start_fixture = Fixture.get_by_id(db, start_fixture_id)
            if start_fixture.tournament_id != tournament.id:
                raise ValueError(f'Fixture {start_fixture_id} is not in tournament {tournament.code}.')
            start_kickoff_at = start_fixture.kickoff_at

        statement = Fixture.score_update_statement(
            tournament.id,
            start_fixture_id=start_fixture_id,
            start_kickoff_at=start_kickoff_at,
            only_unscored=start_fixture_id is None,
        )
        fixtures = db.scalars(statement.limit(count)).all()
        return [
            {
                'id': fixture.id,
                'home_team': fixture.home_team,
                'away_team': fixture.away_team,
                'home_score': fixture.home_score,
                'away_score': fixture.away_score,
                'red_card_given': self._actual_red_card_given(fixture),
            }
            for fixture in fixtures
        ]

    @db_transaction
    def list_active_tournaments(self, page=1, page_size=10, db=None):
        tournament_page = paginate_query(db, Tournament.active_statement(), page=page, page_size=page_size)
        items = []
        for tournament in tournament_page.items:
            items.append(
                {
                    'code': tournament.code,
                    'name': tournament.name,
                    'prediction_users': Tournament.count_prediction_users(db, tournament.id),
                }
            )
        return tournament_page, items

    @db_transaction
    def list_fixtures(self, discord_user, tournament_code, fixture_filter='all', page=1, page_size=10, db=None):
        tournament = Tournament.get_by_code(db, tournament_code)
        user = User.find_by_discord_user_id(db, discord_user.id)
        user_id = user.id if user else 0
        fixture_page = paginate_query(
            db,
            Fixture.fixture_list_statement(tournament.id, user_id=user_id, fixture_filter=fixture_filter),
            page=page,
            page_size=page_size,
        )
        items = [self._fixture_item(db, fixture, user_id) for fixture in fixture_page.items]
        return {
            'page': fixture_page,
            'items': items,
            'tournament_code': tournament.code,
            'tournament_name': tournament.name,
            'fixture_filter': fixture_filter,
        }

    @db_transaction
    def show_rules(self, tournament_code=None, db=None):
        ruleset = Ruleset.get_for_tournament_code(db, tournament_code) if tournament_code else Ruleset.find_by_name(db, 'default')
        if ruleset is None:
            raise LookupError('Ruleset was not found.')
        return ruleset.name, ruleset.config_json

    @db_transaction
    def upsert_ruleset(self, data, db):
        ruleset_name = data.get('name') or 'default'
        config_json = self._parse_ruleset_config(data.get('config_json'))
        ruleset, created = Ruleset.upsert_from_dict(
            db,
            {
                'name': ruleset_name,
                'config_json': config_json,
            },
        )
        action = 'Created' if created else 'Updated'
        return f'{action} ruleset {ruleset.name}.'

    @db_transaction
    def add_tournament(self, data, db):
        ruleset = self._get_or_create_ruleset(db, data)
        tournament, created = Tournament.upsert_from_dict(
            db,
            {
                'name': data['name'],
                'code': data['code'],
                'status': data.get('status', 'active'),
                'ruleset_id': ruleset.id,
            },
        )
        action = 'Created' if created else 'Updated'
        return f'{action} tournament {tournament.name} ({tournament.code}).'

    @db_transaction
    def upsert_fixture(self, data, db):
        tournament = Tournament.get_by_code(db, data['tournament_code'])
        fixture, created = Fixture.upsert_from_dict(
            db,
            {
                'tournament_id': tournament.id,
                'home_team': data['home_team'],
                'away_team': data['away_team'],
                'kickoff_at': data['kickoff_at'],
                'status': data.get('status', 'scheduled'),
            },
        )
        action = 'Created' if created else 'Updated'
        return f'{action} fixture #{fixture.id}: {fixture.home_team} vs {fixture.away_team}.'

    @db_transaction
    def update_fixture_score(self, data, db):
        fixture = Fixture.get_by_id(db, data['fixture_id'])
        Fixture.apply_score_update(fixture, data)
        red_card_given = data.get('red_card_given')
        if red_card_given is not None:
            FixtureEvent.set_boolean_event(
                db,
                fixture.id,
                'red_card_given',
                parse_yes_no(red_card_given, 'Actual red card given'),
            )
        db.flush()
        return f'Updated final score for fixture #{fixture.id}: {fixture.home_score}-{fixture.away_score}.'

    @db_transaction
    def upsert_fixture_event(self, data, db):
        fixture = Fixture.get_by_id(db, data['fixture_id'])
        fixture_event, created = FixtureEvent.upsert_from_dict(
            db,
            {
                'fixture_id': fixture.id,
                'event_type': data['event_type'],
                'player_name': data['player_name'],
                'team_name': data['team_name'],
            },
        )
        action = 'Created' if created else 'Updated'
        return f'{action} event #{fixture_event.id}: {fixture_event.event_type} by {fixture_event.player_name}.'

    def _get_or_create_ruleset(self, db, data):
        ruleset_name = data.get('ruleset_name') or 'default'
        config_json = self._parse_ruleset_config(data.get('ruleset_config_json'))

        ruleset, _ = Ruleset.get_or_create_from_dict(
            db,
            {
                'name': ruleset_name,
                'config_json': config_json,
            },
        )
        return ruleset

    def _parse_ruleset_config(self, config_json):
        if isinstance(config_json, str) and config_json.strip():
            return validate_ruleset_config(json.loads(config_json))
        if config_json:
            return validate_ruleset_config(config_json)
        return validate_ruleset_config(DEFAULT_RULESET_CONFIG)

    def _actual_red_card_given(self, fixture):
        red_card_given_events = [
            event for event in fixture.fixture_events if event.event_type == 'red_card_given'
        ]
        if red_card_given_events:
            return red_card_given_events[-1].player_name
        if any(event.event_type == 'red_card' for event in fixture.fixture_events):
            return 'true'
        return None

    def _fixture_item(self, db, fixture, user_id):
        prediction = ScorePrediction.find_by_user_and_fixture(db, user_id, fixture.id) if user_id else None
        event_predictions = (
            EventPrediction.find_by_user_and_fixture(db, user_id, fixture.id)
            if user_id
            else []
        )
        goalscorer_predictions = [
            event for event in event_predictions if event.event_type == 'goalscorer'
        ]
        red_card_given_prediction = next(
            (event.player_name for event in event_predictions if event.event_type == 'red_card_given'),
            None,
        )
        fixture_updated = fixture.home_score is not None and fixture.away_score is not None
        score_points = prediction.points_awarded if prediction else 0
        event_points = sum(event.points_awarded for event in event_predictions)
        return {
            'id': fixture.id,
            'kickoff_at': fixture.kickoff_at,
            'home_team': fixture.home_team,
            'away_team': fixture.away_team,
            'predicted_home_score': prediction.predicted_home_score if prediction else None,
            'predicted_away_score': prediction.predicted_away_score if prediction else None,
            'home_score': fixture.home_score,
            'away_score': fixture.away_score,
            'predicted_goalscorers': [event.player_name for event in goalscorer_predictions],
            'predicted_red_card_given': red_card_given_prediction,
            'points_earned': score_points + event_points if fixture_updated else None,
        }
