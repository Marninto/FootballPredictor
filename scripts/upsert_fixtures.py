import argparse
import json
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.load_env import load_env_file
from services.tournament_service import TournamentService


DEFAULT_FIXTURE_FILE = 'epl_2026_fixtures_simplified.json'
REQUIRED_FIXTURE_KEYS = {'home_team', 'away_team', 'kickoff_at'}


def _load_fixtures(path):
    with open(path, encoding='utf-8') as fixture_file:
        data = json.load(fixture_file)

    if isinstance(data, dict) and isinstance(data.get('fixtures'), list):
        data = data['fixtures']

    if not isinstance(data, list):
        raise ValueError('Fixture file must contain a JSON list or an object with a fixtures list.')

    fixtures = []
    for index, fixture in enumerate(data, start=1):
        if not isinstance(fixture, dict):
            raise ValueError(f'Fixture #{index} must be a JSON object.')
        missing_keys = REQUIRED_FIXTURE_KEYS - set(fixture)
        if missing_keys:
            missing = ', '.join(sorted(missing_keys))
            raise ValueError(f'Fixture #{index} is missing: {missing}.')
        fixtures.append(fixture)
    return fixtures


def main():
    parser = argparse.ArgumentParser(description='Create or update fixtures for a tournament.')
    parser.add_argument('tournament_code', help='Tournament code to attach fixtures to.')
    parser.add_argument(
        '--file',
        default=DEFAULT_FIXTURE_FILE,
        help=f'Fixture JSON file path. Defaults to {DEFAULT_FIXTURE_FILE}.',
    )
    args = parser.parse_args()

    load_env_file()
    fixtures = _load_fixtures(args.file)
    tournament_service = TournamentService()
    created_count = 0
    updated_count = 0

    for fixture in fixtures:
        message = tournament_service.upsert_fixture(
            {
                'tournament_code': args.tournament_code,
                'home_team': fixture['home_team'],
                'away_team': fixture['away_team'],
                'kickoff_at': fixture['kickoff_at'],
                'status': fixture.get('status', 'scheduled'),
            }
        )
        if message.startswith('Created '):
            created_count += 1
        elif message.startswith('Updated '):
            updated_count += 1

    print(
        f'Processed {len(fixtures)} fixtures for {args.tournament_code}. '
        f'Created: {created_count}. Updated: {updated_count}.'
    )


if __name__ == '__main__':
    main()
