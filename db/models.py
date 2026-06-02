from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


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
    discord_user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    discord_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prediction_visibility: Mapped[str] = mapped_column(String(20), nullable=False, default='public', server_default='public')

    score_predictions = relationship('ScorePrediction', back_populates='user')
    event_predictions = relationship('EventPrediction', back_populates='user')
    leaderboard_entries = relationship('LeaderboardEntry', back_populates='user')


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


class Ruleset(TimestampMixin, Base):
    __tablename__ = 'rulesets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    tournaments = relationship('Tournament', back_populates='ruleset')


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
    kickoff_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='scheduled', server_default='scheduled')
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tournament = relationship('Tournament', back_populates='fixtures')
    score_predictions = relationship('ScorePrediction', back_populates='fixture')
    event_predictions = relationship('EventPrediction', back_populates='fixture')
    fixture_events = relationship('FixtureEvent', back_populates='fixture')


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


class EventPrediction(TimestampMixin, Base):
    __tablename__ = 'event_predictions'
    __table_args__ = (
        UniqueConstraint('user_id', 'fixture_id', 'event_type', 'player_name', 'team_name', name='uq_event_predictions_user_fixture_event_player_team'),
        Index('ix_event_predictions_user_fixture', 'user_id', 'fixture_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    fixture_id: Mapped[int] = mapped_column(ForeignKey('fixtures.id'), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_name: Mapped[str] = mapped_column(String(255), nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    scoring_reason_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user = relationship('User', back_populates='event_predictions')
    fixture = relationship('Fixture', back_populates='event_predictions')


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
