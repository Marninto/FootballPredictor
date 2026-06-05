import argparse
import json
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.load_env import load_env_file
from domain.scoring_rules import DEFAULT_RULESET_CONFIG
from services.tournament_service import TournamentService


def main():
    parser = argparse.ArgumentParser(description='Create or update a ruleset.')
    parser.add_argument('--name', default='default', help='Ruleset name. Defaults to default.')
    parser.add_argument('--config-file', help='Optional JSON config file path.')
    args = parser.parse_args()

    load_env_file()
    config_json = DEFAULT_RULESET_CONFIG
    if args.config_file:
        with open(args.config_file, encoding='utf-8') as config_file:
            config_json = json.load(config_file)

    message = TournamentService().upsert_ruleset(
        {
            'name': args.name,
            'config_json': config_json,
        }
    )
    print(message)


if __name__ == '__main__':
    main()
