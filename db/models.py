from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, delete, exists, func, select, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from utils.time import parse_datetime, utc_now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = 'users'
    __table_args__ = (
        Index('ix_users_discord_user_id', 'discord_user_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    discord_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prediction_visibility: Mapped[str] = mapped_column(String(20), nullable=False, default='public', server_default='public')

    score_predictions = relationship('ScorePrediction', back_populates='user')
    event_predictions = relationship('EventPrediction', back_populates='user')
    leaderboard_entries = relationship('LeaderboardEntry', back_populates='user')

    @classmethod
    def find_by_discord_user_id(cls, db, discord_user_id):
        return db.scalar(select(cls).where(cls.discord_user_id == int(discord_user_id)))

    @classmethod
    def get_or_create_from_discord(cls, db, discord_user_id, display_name):
        user = cls.find_by_discord_user_id(db, discord_user_id)
        if user is not None:
            user.discord_display_name = display_name
            return user, False

        user = cls(discord_user_id=int(discord_user_id), discord_display_name=display_name)
        db.add(user)
        db.flush()
        return user, True

    @classmethod
    def set_prediction_visibility(cls, user, visibility):
        user.prediction_visibility = visibility

    @classmethod
    def users_by_ids_statement(cls, user_ids):
        return select(cls).where(cls.id.in_([int(user_id) for user_id in user_ids])).order_by(cls.id)


class Tournament(TimestampMixin, Base):
    __tablename__ = 'tournaments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='active', server_default='active')
    ruleset_id: Mapped[int] = mapped_column(ForeignKey('rulesets.id'), nullable=False)

    ruleset = relationship('Ruleset', back_populates='tournaments')
    fixtures = relationship('Fixture', back_populates='tournament')
    leaderboard_entries = relationship('LeaderboardEntry', back_populates='tournament')

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data['name'].strip(),
            code=data['code'].strip().upper(),
            status=data.get('status', 'active'),
            ruleset_id=data['ruleset_id'],
        )

    @classmethod
    def find_by_code(cls, db, code):
        return db.scalar(select(cls).where(cls.code == code.strip().upper()))

    @classmethod
    def active_statement(cls):
        return select(cls).where(cls.status == 'active').order_by(cls.code)

    @classmethod
    def count_prediction_users(cls, db, tournament_id):
        score_user_ids = select(ScorePrediction.user_id).join(Fixture).where(Fixture.tournament_id == tournament_id)
        event_user_ids = select(EventPrediction.user_id).join(Fixture).where(Fixture.tournament_id == tournament_id)
        return len({row[0] for row in db.execute(score_user_ids.union(event_user_ids)).all()})

    @classmethod
    def get_by_code(cls, db, code):
        tournament = cls.find_by_code(db, code)
        if tournament is None:
            raise LookupError(f'Tournament {code} was not found.')
        return tournament

    @classmethod
    def upsert_from_dict(cls, db, data):
        tournament = cls.find_by_code(db, data['code'])
        created = tournament is None
        if created:
            tournament = cls.from_dict(data)
            db.add(tournament)
        else:
            tournament.name = data['name'].strip()
            tournament.status = data.get('status', 'active')
            tournament.ruleset_id = data['ruleset_id']

        db.flush()
        return tournament, created


class Ruleset(TimestampMixin, Base):
    __tablename__ = 'rulesets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    tournaments = relationship('Tournament', back_populates='ruleset')

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data['name'].strip(),
            config_json=data['config_json'],
        )

    @classmethod
    def find_by_name(cls, db, name):
        return db.scalar(select(cls).where(cls.name == name.strip()))

    @classmethod
    def get_or_create_from_dict(cls, db, data):
        ruleset = cls.find_by_name(db, data['name'])
        if ruleset is not None:
            return ruleset, False

        ruleset = cls.from_dict(data)
        db.add(ruleset)
        db.flush()
        return ruleset, True

    @classmethod
    def upsert_from_dict(cls, db, data):
        ruleset = cls.find_by_name(db, data['name'])
        created = ruleset is None
        if created:
            ruleset = cls.from_dict(data)
            db.add(ruleset)
        else:
            ruleset.config_json = data['config_json']

        db.flush()
        return ruleset, created

    @classmethod
    def get_for_tournament_code(cls, db, tournament_code):
        tournament = Tournament.get_by_code(db, tournament_code)
        return tournament.ruleset


class Announcement(TimestampMixin, Base):
    __tablename__ = 'announcements'
    __table_args__ = (
        UniqueConstraint('announcement_type', name='uq_announcements_announcement_type'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    announcement_type: Mapped[str] = mapped_column(String(100), nullable=False)
    last_triggered: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_gap: Mapped[int] = mapped_column(Integer, nullable=False)

    @classmethod
    def all_statement(cls):
        return select(cls).order_by(cls.announcement_type)

    @classmethod
    def find_by_type(cls, db, announcement_type):
        return db.scalar(select(cls).where(cls.announcement_type == announcement_type.strip()))

    @classmethod
    def upsert_from_dict(cls, db, data):
        announcement = cls.find_by_type(db, data['announcement_type'])
        created = announcement is None
        if created:
            announcement = cls(
                announcement_type=data['announcement_type'].strip(),
                trigger_gap=int(data['trigger_gap']),
            )
            db.add(announcement)
        else:
            announcement.trigger_gap = int(data['trigger_gap'])

        db.flush()
        return announcement, created

    @classmethod
    def mark_triggered(cls, announcement, triggered_at):
        announcement.last_triggered = triggered_at


class Fixture(TimestampMixin, Base):
    __tablename__ = 'fixtures'
    __table_args__ = (
        UniqueConstraint('tournament_id', 'home_team', 'away_team', 'kickoff_at', name='uq_fixtures_tournament_match_kickoff'),
        Index('ix_fixtures_tournament_kickoff', 'tournament_id', 'kickoff_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey('tournaments.id'), nullable=False)
    home_team: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team: Mapped[str] = mapped_column(String(255), nullable=False)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='scheduled', server_default='scheduled')
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tournament = relationship('Tournament', back_populates='fixtures')
    score_predictions = relationship('ScorePrediction', back_populates='fixture')
    event_predictions = relationship('EventPrediction', back_populates='fixture')
    fixture_events = relationship('FixtureEvent', back_populates='fixture')

    @classmethod
    def from_dict(cls, data):
        return cls(
            tournament_id=data['tournament_id'],
            home_team=data['home_team'].strip(),
            away_team=data['away_team'].strip(),
            kickoff_at=parse_datetime(data['kickoff_at']),
            status=data.get('status', 'scheduled'),
            home_score=data.get('home_score'),
            away_score=data.get('away_score'),
        )

    @classmethod
    def get_by_id(cls, db, fixture_id):
        fixture = db.get(cls, int(fixture_id))
        if fixture is None:
            raise LookupError(f'Fixture {fixture_id} was not found.')
        return fixture

    @classmethod
    def fixture_list_statement(cls, tournament_id, user_id=None, fixture_filter='all'):
        statement = select(cls).where(cls.tournament_id == tournament_id).order_by(cls.kickoff_at, cls.id)
        if fixture_filter == 'predicted':
            statement = statement.where(
                (
                    exists().where(
                        ScorePrediction.fixture_id == cls.id,
                        ScorePrediction.user_id == int(user_id),
                    )
                )
                | (
                    exists().where(
                        EventPrediction.fixture_id == cls.id,
                        EventPrediction.user_id == int(user_id),
                    )
                )
            )
        elif fixture_filter == 'open':
            statement = statement.where(
                cls.status == 'scheduled',
                cls.kickoff_at > utc_now(),
                ~exists().where(
                    ScorePrediction.fixture_id == cls.id,
                    ScorePrediction.user_id == int(user_id),
                ),
            )
        return statement

    @classmethod
    def open_unpredicted_statement(cls, tournament_id, user_id, start_fixture_id=None):
        statement = select(cls).where(
            cls.tournament_id == int(tournament_id),
            cls.status == 'scheduled',
            cls.kickoff_at > utc_now(),
            ~exists().where(
                ScorePrediction.fixture_id == cls.id,
                ScorePrediction.user_id == int(user_id),
            ),
        )
        if start_fixture_id is not None:
            statement = statement.where(cls.id >= int(start_fixture_id))
        return statement.order_by(cls.kickoff_at, cls.id)

    @classmethod
    def upcoming_statement(cls, start_at, end_at):
        return (
            select(cls)
            .join(Tournament)
            .where(
                cls.status == 'scheduled',
                cls.kickoff_at >= start_at,
                cls.kickoff_at <= end_at,
            )
            .order_by(Tournament.name, cls.kickoff_at, cls.id)
        )

    @classmethod
    def find_by_match_key(cls, db, data):
        kickoff_at = parse_datetime(data['kickoff_at'])
        return db.scalar(
            select(cls).where(
                cls.tournament_id == data['tournament_id'],
                cls.home_team == data['home_team'].strip(),
                cls.away_team == data['away_team'].strip(),
                cls.kickoff_at == kickoff_at,
            )
        )

    @classmethod
    def upsert_from_dict(cls, db, data):
        fixture = cls.find_by_match_key(db, data)
        created = fixture is None
        if created:
            fixture = cls.from_dict(data)
            db.add(fixture)
        else:
            fixture.status = data.get('status', 'scheduled')

        db.flush()
        return fixture, created

    @classmethod
    def score_update_from_dict(cls, data):
        return {
            'home_score': int(data['home_score']),
            'away_score': int(data['away_score']),
            'status': data.get('status', 'completed'),
        }

    @classmethod
    def apply_score_update(cls, fixture, data):
        score_data = cls.score_update_from_dict(data)
        fixture.home_score = score_data['home_score']
        fixture.away_score = score_data['away_score']
        fixture.status = score_data['status']

    @classmethod
    def revert_score(cls, fixture):
        fixture.home_score = None
        fixture.away_score = None
        fixture.status = 'scheduled'


class ScorePrediction(TimestampMixin, Base):
    __tablename__ = 'score_predictions'
    __table_args__ = (
        UniqueConstraint('user_id', 'fixture_id', name='uq_score_predictions_user_fixture'),
        Index('ix_score_predictions_user_fixture', 'user_id', 'fixture_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    fixture_id: Mapped[int] = mapped_column(ForeignKey('fixtures.id'), nullable=False)
    predicted_home_score: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_away_score: Mapped[int] = mapped_column(Integer, nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    scoring_reason_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user = relationship('User', back_populates='score_predictions')
    fixture = relationship('Fixture', back_populates='score_predictions')

    @classmethod
    def find_by_user_and_fixture(cls, db, user_id, fixture_id):
        return db.scalar(
            select(cls).where(
                cls.user_id == int(user_id),
                cls.fixture_id == int(fixture_id),
            )
        )

    @classmethod
    def upsert_from_dict(cls, db, data):
        prediction = cls.find_by_user_and_fixture(db, data['user_id'], data['fixture_id'])
        created = prediction is None
        if created:
            prediction = cls(
                user_id=int(data['user_id']),
                fixture_id=int(data['fixture_id']),
                predicted_home_score=int(data['predicted_home_score']),
                predicted_away_score=int(data['predicted_away_score']),
            )
            db.add(prediction)
        else:
            prediction.predicted_home_score = int(data['predicted_home_score'])
            prediction.predicted_away_score = int(data['predicted_away_score'])
            prediction.points_awarded = 0
            prediction.scoring_reason_json = None

        db.flush()
        return prediction, created

    @classmethod
    def find_by_fixture(cls, db, fixture_id):
        return db.scalars(select(cls).where(cls.fixture_id == int(fixture_id))).all()

    @classmethod
    def count_distinct_users_for_tournament(cls, db, tournament_id):
        return int(
            db.scalar(
                select(func.count(func.distinct(cls.user_id))).join(Fixture).where(Fixture.tournament_id == tournament_id)
            )
        )

    @classmethod
    def find_user_ids_for_tournament(cls, db, tournament_id):
        return [
            row[0]
            for row in db.execute(
                select(func.distinct(cls.user_id)).join(Fixture).where(Fixture.tournament_id == tournament_id)
            ).all()
        ]

    @classmethod
    def award_points(cls, prediction, points, reason):
        prediction.points_awarded = points
        prediction.scoring_reason_json = {
            'reason': reason,
            'points': points,
        }

    @classmethod
    def reset_points(cls, prediction):
        prediction.points_awarded = 0
        prediction.scoring_reason_json = None


class EventPrediction(TimestampMixin, Base):
    __tablename__ = 'event_predictions'
    __table_args__ = (
        UniqueConstraint('user_id', 'fixture_id', 'event_type', name='uq_event_predictions_user_fixture_event'),
        Index('ix_event_predictions_user_fixture', 'user_id', 'fixture_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    fixture_id: Mapped[int] = mapped_column(ForeignKey('fixtures.id'), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    scoring_reason_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user = relationship('User', back_populates='event_predictions')
    fixture = relationship('Fixture', back_populates='event_predictions')

    @classmethod
    def find_by_prediction_key(cls, db, data):
        return db.scalar(
            select(cls).where(
                cls.user_id == int(data['user_id']),
                cls.fixture_id == int(data['fixture_id']),
                cls.event_type == data['event_type'].strip(),
            )
        )

    @classmethod
    def upsert_from_dict(cls, db, data):
        prediction = cls.find_by_prediction_key(db, data)
        created = prediction is None
        if created:
            prediction = cls(
                user_id=int(data['user_id']),
                fixture_id=int(data['fixture_id']),
                event_type=data['event_type'].strip(),
                player_name=data['player_name'].strip(),
            )
            db.add(prediction)
        else:
            prediction.player_name = data['player_name'].strip()
            prediction.points_awarded = 0
            prediction.scoring_reason_json = None

        db.flush()
        return prediction, created

    @classmethod
    def find_by_fixture(cls, db, fixture_id):
        return db.scalars(select(cls).where(cls.fixture_id == int(fixture_id))).all()

    @classmethod
    def find_by_user_and_fixture(cls, db, user_id, fixture_id):
        return db.scalars(
            select(cls).where(
                cls.user_id == int(user_id),
                cls.fixture_id == int(fixture_id),
            )
        ).all()

    @classmethod
    def count_distinct_users_for_tournament(cls, db, tournament_id):
        return int(
            db.scalar(
                select(func.count(func.distinct(cls.user_id))).join(Fixture).where(Fixture.tournament_id == tournament_id)
            )
        )

    @classmethod
    def find_user_ids_for_tournament(cls, db, tournament_id):
        return [
            row[0]
            for row in db.execute(
                select(func.distinct(cls.user_id)).join(Fixture).where(Fixture.tournament_id == tournament_id)
            ).all()
        ]

    @classmethod
    def award_points(cls, prediction, points, reason):
        prediction.points_awarded = points
        prediction.scoring_reason_json = {
            'reason': reason,
            'points': points,
        }


class FixtureEvent(TimestampMixin, Base):
    __tablename__ = 'fixture_events'
    __table_args__ = (
        UniqueConstraint('fixture_id', 'event_type', 'player_name', 'team_name', name='uq_fixture_events_fixture_event_player_team'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey('fixtures.id'), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_name: Mapped[str] = mapped_column(String(255), nullable=False)

    fixture = relationship('Fixture', back_populates='fixture_events')

    @classmethod
    def from_dict(cls, data):
        return cls(
            fixture_id=int(data['fixture_id']),
            event_type=data['event_type'].strip(),
            player_name=data['player_name'].strip(),
            team_name=data['team_name'].strip(),
        )

    @classmethod
    def find_by_event_key(cls, db, data):
        return db.scalar(
            select(cls).where(
                cls.fixture_id == int(data['fixture_id']),
                cls.event_type == data['event_type'].strip(),
                cls.player_name == data['player_name'].strip(),
                cls.team_name == data['team_name'].strip(),
            )
        )

    @classmethod
    def upsert_from_dict(cls, db, data):
        fixture_event = cls.find_by_event_key(db, data)
        created = fixture_event is None
        if created:
            fixture_event = cls.from_dict(data)
            db.add(fixture_event)

        db.flush()
        return fixture_event, created

    @classmethod
    def delete_by_fixture_and_type(cls, db, fixture_id, event_type):
        result = db.execute(
            delete(cls).where(
                cls.fixture_id == int(fixture_id),
                cls.event_type == event_type.strip(),
            )
        )
        return result.rowcount or 0


class LeaderboardEntry(TimestampMixin, Base):
    __tablename__ = 'leaderboard_entries'
    __table_args__ = (
        UniqueConstraint('tournament_id', 'user_id', name='uq_leaderboard_entries_tournament_user'),
        Index('ix_leaderboard_entries_tournament_total_points', 'tournament_id', text('total_points DESC')),
        Index('ix_leaderboard_entries_user_id', 'user_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey('tournaments.id'), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    score_prediction_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    event_prediction_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')

    tournament = relationship('Tournament', back_populates='leaderboard_entries')
    user = relationship('User', back_populates='leaderboard_entries')

    @classmethod
    def find_by_tournament_and_user(cls, db, tournament_id, user_id):
        return db.scalar(
            select(cls).where(
                cls.tournament_id == tournament_id,
                cls.user_id == int(user_id),
            )
        )

    @classmethod
    def point_column(cls, point_filter):
        if point_filter == 'event':
            return cls.event_prediction_points
        if point_filter == 'prediction':
            return cls.score_prediction_points
        return cls.total_points

    @classmethod
    def leaderboard_statement(cls, tournament_id=None, point_filter='total'):
        point_column = cls.point_column(point_filter)
        tournament_filter = cls.tournament_id.is_(None) if tournament_id is None else cls.tournament_id == tournament_id
        return (
            select(cls)
            .join(User)
            .where(tournament_filter)
            .order_by(point_column.desc(), cls.total_points.desc(), cls.id.asc())
        )

    @classmethod
    def rank_for_user(cls, db, tournament_id, user_id, point_filter='total'):
        entry = cls.find_by_tournament_and_user(db, tournament_id, user_id)
        if entry is None:
            return None

        point_column = cls.point_column(point_filter)
        entry_points = getattr(entry, point_column.key)
        tournament_filter = cls.tournament_id.is_(None) if tournament_id is None else cls.tournament_id == tournament_id
        return int(
            db.scalar(
                select(func.count(cls.id) + 1).where(
                    tournament_filter,
                    point_column > entry_points,
                )
            )
        )

    @classmethod
    def global_entry_for_user(cls, db, user_id):
        return cls.find_by_tournament_and_user(db, None, user_id)

    @classmethod
    def best_tournament_entry_for_user(cls, db, user_id):
        return db.scalar(
            select(cls)
            .where(cls.user_id == int(user_id), cls.tournament_id.is_not(None))
            .order_by(cls.total_points.desc(), cls.id.asc())
            .limit(1)
        )

    @classmethod
    def rank_for_total_points(cls, db, entry):
        if entry is None or entry.total_points <= 0:
            return None
        return int(
            db.scalar(
                select(func.count(cls.id) + 1).where(
                    cls.tournament_id.is_(None) if entry.tournament_id is None else cls.tournament_id == entry.tournament_id,
                    cls.total_points > entry.total_points,
                )
            )
        )

    @classmethod
    def rank_for_event_points(cls, db, entry):
        if entry is None or entry.event_prediction_points <= 0:
            return None
        return int(
            db.scalar(
                select(func.count(cls.id) + 1).where(
                    cls.tournament_id.is_(None) if entry.tournament_id is None else cls.tournament_id == entry.tournament_id,
                    cls.event_prediction_points > entry.event_prediction_points,
                )
            )
        )

    @classmethod
    def get_or_create(cls, db, tournament_id, user_id):
        entry = cls.find_by_tournament_and_user(db, tournament_id, user_id)
        if entry is not None:
            return entry, False

        entry = cls(tournament_id=tournament_id, user_id=int(user_id))
        db.add(entry)
        db.flush()
        return entry, True

    @classmethod
    def apply_points(cls, entry, score_points, event_points):
        entry.score_prediction_points = score_points
        entry.event_prediction_points = event_points
        entry.total_points = score_points + event_points
