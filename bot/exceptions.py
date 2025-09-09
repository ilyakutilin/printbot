class SettingsError(Exception):
    """Base class for settings validation."""


class MissingEnvVarError(SettingsError):
    """Raised if a required env var is missing."""

    def __init__(self, env_var: str) -> None:
        super().__init__(f"No {env_var} value in .env.")


class IncorrectUserIDError(SettingsError):
    """Raised if the user ID is not an integer."""

    def __init__(self, user_ids: list[str]) -> None:
        super().__init__(f"Incorrect Telegram User ID(s): {', '.join(user_ids)}.")
