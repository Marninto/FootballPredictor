from datetime import timedelta

from db.database import db_transaction
from db.models import Announcement, EventPrediction, Fixture, ScorePrediction, User
from utils.time import utc_now


FIXTURE_ANNOUNCEMENT_2_DAYS = 'fixture_announcement_2_days'
SUPPORTED_ANNOUNCEMENT_TYPES = {FIXTURE_ANNOUNCEMENT_2_DAYS}


class AnnouncementService:
    @db_transaction
    def upsert_announcement(self, data, db):
        announcement_type = data['announcement_type'].strip()
        if announcement_type not in SUPPORTED_ANNOUNCEMENT_TYPES:
            raise ValueError(f'Unsupported announcement type: {announcement_type}.')

        trigger_gap = int(data['trigger_gap'])
        if trigger_gap <= 0:
            raise ValueError('trigger_gap must be greater than 0 minutes.')

        announcement, created = Announcement.upsert_from_dict(
            db,
            {
                'announcement_type': announcement_type,
                'trigger_gap': trigger_gap,
            },
        )
        action = 'Created' if created else 'Updated'
        return f'{action} announcement {announcement.announcement_type} with trigger gap {announcement.trigger_gap} minutes.'

    @db_transaction
    def due_announcements(self, db):
        now = utc_now()
        due = []
        for announcement in db.scalars(Announcement.all_statement()).all():
            if self._is_due(announcement, now):
                due.append(
                    {
                        'id': announcement.id,
                        'announcement_type': announcement.announcement_type,
                    }
                )
        return due

    @db_transaction
    def status_rows(self, db):
        now = utc_now()
        rows = []
        for announcement in db.scalars(Announcement.all_statement()).all():
            next_trigger_at = self._next_trigger_at(announcement, now)
            rows.append(
                {
                    'id': announcement.id,
                    'announcement_type': announcement.announcement_type,
                    'trigger_gap': announcement.trigger_gap,
                    'last_triggered': announcement.last_triggered,
                    'next_trigger_at': next_trigger_at,
                    'due': self._is_due(announcement, now),
                }
            )
        return rows

    @db_transaction
    def get_announcement_by_type(self, announcement_type, db):
        announcement = Announcement.find_by_type(db, announcement_type)
        if announcement is None:
            raise LookupError(f'Announcement {announcement_type} was not found.')
        return {
            'id': announcement.id,
            'announcement_type': announcement.announcement_type,
        }

    @db_transaction
    def mark_triggered(self, announcement_id, db):
        announcement = db.get(Announcement, int(announcement_id))
        if announcement is None:
            raise LookupError(f'Announcement {announcement_id} was not found.')
        Announcement.mark_triggered(announcement, utc_now())
        db.flush()

    @db_transaction
    def upcoming_fixture_groups(self, db):
        now = utc_now()
        end_at = now + timedelta(hours=48)
        fixtures = db.scalars(Fixture.upcoming_statement(now, end_at)).all()
        groups = {}
        for fixture in fixtures:
            tournament = fixture.tournament
            group = groups.setdefault(
                tournament.id,
                {
                    'tournament_name': tournament.name,
                    'users': self._prediction_users_for_tournament(db, tournament.id),
                    'fixtures': [],
                },
            )
            group['fixtures'].append(
                {
                    'id': fixture.id,
                    'home_team': fixture.home_team,
                    'away_team': fixture.away_team,
                }
            )
        return list(groups.values())

    def _is_due(self, announcement, now):
        if announcement.last_triggered is None:
            return True
        last_triggered = announcement.last_triggered
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=now.tzinfo)
        return now - last_triggered >= timedelta(minutes=announcement.trigger_gap)

    def _next_trigger_at(self, announcement, now):
        if announcement.last_triggered is None:
            return now
        last_triggered = announcement.last_triggered
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=now.tzinfo)
        return last_triggered + timedelta(minutes=announcement.trigger_gap)

    def _prediction_users_for_tournament(self, db, tournament_id):
        score_user_ids = ScorePrediction.find_user_ids_for_tournament(db, tournament_id)
        event_user_ids = EventPrediction.find_user_ids_for_tournament(db, tournament_id)
        user_ids = sorted(set(score_user_ids) | set(event_user_ids))
        if not user_ids:
            return []
        return [
            {
                'discord_user_id': user.discord_user_id,
                'display_name': user.discord_display_name,
            }
            for user in db.scalars(User.users_by_ids_statement(user_ids)).all()
        ]
