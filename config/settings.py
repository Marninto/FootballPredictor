import os
from dataclasses import dataclass


DEFAULT_DATABASE_URL = 'sqlite:///./football_predictor.db'
DATABASE_URL = os.getenv('DATABASE_URL', DEFAULT_DATABASE_URL)


@dataclass(frozen=True)
class Settings:
    application_id: int
    public_key: str
    admin_user_ids: list[int]
    bot_token: str
    database_url: str
    command_prefix: str = '!'


def _required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'{name} is missing from .env')
    return value


def _parse_int_list(value):
    return [int(item.strip()) for item in value.split(',') if item.strip()]


def load_settings():
    return Settings(
        application_id=int(_required_env('APPLICATION_ID')),
        public_key=_required_env('PUBLIC_KEY'),
        admin_user_ids=_parse_int_list(_required_env('ADMIN_USER_IDS')),
        bot_token=_required_env('BOT_TOKEN'),
        database_url=os.getenv('DATABASE_URL', DEFAULT_DATABASE_URL),
        command_prefix=os.getenv('COMMAND_PREFIX', '!'),
    )
