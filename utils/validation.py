import re
from datetime import timedelta

from utils.time import utc_now


PLAYER_NAME_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')


def require_non_empty(value, field_name):
    if not value:
        raise ValueError(f'{field_name} is required')
    return value


def validate_player_name(player_name):
    require_non_empty(player_name, 'player_name')
    if not PLAYER_NAME_PATTERN.fullmatch(player_name):
        raise ValueError('Player name can only contain letters, numbers, underscores, or hyphens.')
    return player_name


def validate_fixture_open_for_prediction(fixture):
    if fixture.status != 'scheduled':
        raise ValueError('Predictions are closed for this fixture.')

    cutoff_at = fixture.kickoff_at - timedelta(minutes=30)
    if utc_now() >= cutoff_at:
        raise ValueError('Predictions close 30 minutes before kickoff.')
