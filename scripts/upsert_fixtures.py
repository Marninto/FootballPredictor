import argparse
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.load_env import load_env_file
from services.tournament_service import TournamentService


def main():
    parser = argparse.ArgumentParser(description='Create or update fixtures for a tournament.')
    parser.add_argument('tournament_code', help='Tournament code to attach fixtures to.')
    parser.add_argument('filename', help='Fixture JSON filename inside fixtures directory, without .json.')
    args = parser.parse_args()

    load_env_file()
    print(TournamentService().import_fixtures(args.tournament_code, args.filename))


if __name__ == '__main__':
    main()
