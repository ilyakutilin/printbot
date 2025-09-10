from bot.bot import build_app
from bot.exceptions import SettingsError
from bot.settings import Settings


def main():
    exit_text = "Bot will be terminated."
    try:
        s = Settings()
    except SettingsError as e:
        # TODO: Switch to logging
        print(f"Project settings validation error: {e} {exit_text}")
        raise SystemExit(1)

    app = build_app(s)

    app.run_polling()


if __name__ == "__main__":
    main()
