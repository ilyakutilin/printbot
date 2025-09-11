from bot.exceptions import SettingsError
from bot.handlers import build_app
from bot.logger import configure_logging
from bot.settings import Settings


def main():
    logger = configure_logging(__name__)

    exit_text = "Bot will be terminated."

    try:
        s = Settings()
    except SettingsError as e:
        logger.error(f"Project settings validation error: {e} {exit_text}")
        raise SystemExit(1)

    logger.info("Building the app.")
    app = build_app(s)

    logger.info("The app has successfully been built, starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
