import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    application_id: int
    public_key: str
    admin_user_ids: list[int]
    bot_token: str
    database_url: str
    bot_announcement_channel_id: int
    command_prefix: str = '!'


def _required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'{name} is missing from .env')
    return value


def _parse_int_list(value):
    return [int(item.strip()) for item in value.split(',') if item.strip()]


def get_database_url():
    url = _required_env('DATABASE_URL')

    if url.startswith('postgresql://'):
        url = url.replace(
            'postgresql://',
            'postgresql+psycopg://',
            1,
        )

    return url


def load_settings():
    return Settings(
        application_id=int(_required_env('APPLICATION_ID')),
        public_key=_required_env('PUBLIC_KEY'),
        admin_user_ids=_parse_int_list(_required_env('ADMIN_USER_IDS')),
        bot_token=_required_env('BOT_TOKEN'),
        database_url=get_database_url(),
        bot_announcement_channel_id=int(_required_env('BOT_ANNOUNCEMENT_CHANNEL_ID')),
        command_prefix=os.getenv('COMMAND_PREFIX', '!'),
    )
