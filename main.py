from bot import create_bot
from config.load_env import load_env_file
from config.settings import load_settings


def main():
    load_env_file()
    settings = load_settings()
    bot = create_bot(settings)
    bot.run(settings.bot_token)


if __name__ == '__main__':
    main()
