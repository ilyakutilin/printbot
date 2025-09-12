import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from bot.exceptions import IncorrectUserIDError, MissingEnvVarError

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = None
if Path.exists(BASE_DIR.parent / ".env"):
    ENV_FILE = BASE_DIR.parent / ".env"
else:
    if Path.exists(BASE_DIR / ".env"):
        ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


class LogSettings:
    def __init__(self) -> None:
        self.log_format: str = os.getenv(
            "LOG_FORMAT",
            "%(asctime)s — %(name)s — %(levelname)s — %(funcName)s:%(lineno)d — %(message)s",
        )
        self.log_dt_fmt: str = os.getenv("LOG_DT_FMT", "%d.%m.%Y %H:%M:%S")
        self.log_level: int = self._validate_log_level("LOG_LEVEL")

    def _validate_log_level(self, env_var: str) -> int:
        val = os.getenv(env_var)

        if not val:
            return logging.INFO

        try:
            return logging.getLevelNamesMapping()[val.strip().upper()]
        except KeyError:
            return logging.INFO


class PrintContext:
    def __init__(self, printer_name: str | None) -> None:
        self.printer_name: str | None = printer_name
        self.allowed_users: tuple[int, ...] | None = self._validate_tg_users(
            "ALLOWED_USERS"
        )
        self.page_confirm_limit: int = self._validate_int("PAGE_CONFIRM_LIMIT", 20)

    def _validate_int(self, env_var: str, default: int) -> int:
        val = os.getenv(env_var)

        if not val:
            return default

        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def _parse_comma_separated(self, env_var: str) -> tuple[str, ...] | None:
        """Splits a comma separated string into a tuple of strings.

        Splits the input string by commas, removes leading and trailing spaces from each
        element, and removes all empty elements. If the input string is empty, None,
        or contains only spaces/commas, returns None.

        Args:
            env_var (str): An environment variable that stores the comma separated
                values.

        Returns:
            parsed (tuple[str, ...] | None): a tuple of non-empty clean strings or None
                if the input data are None or empty after processing.

        Examples:
            >>> parse_comma_separated_strings("a,b,c")
            ('a', 'b', 'c')
            >>> parse_comma_separated_strings(" apple , banana ,  pear ")
            ('apple', 'banana', 'pear')
            >>> parse_comma_separated_strings("")
            None
            >>> parse_comma_separated_strings(None)
            None
            >>> parse_comma_separated_strings(" , , ")
            None
        """
        val = os.getenv(env_var)
        if not val:
            return None
        parsed = tuple([st.strip() for st in val.split(",") if st.strip()])
        if not parsed:
            return None
        return parsed

    def _validate_tg_users(self, env_var: str) -> tuple[int, ...] | None:
        """Validates Telegram User IDs.

        Args:
            env_var (str): An environment variable that stores the comma separated
                values of user ids.

        Raises:
            IncorrectUserIDError: Raised if the user ID is not an integer.

        Returns:
            tuple[str, ...] | None: A tuple of User IDs or None.
        """
        user_ids: tuple[str, ...] | None = self._parse_comma_separated(env_var)

        if not user_ids:
            return None

        wrong_ids: list[str] = []
        correct_ids: list[int] = []
        for user_id in user_ids:
            try:
                correct_ids.append(int(user_id))
            except ValueError:
                wrong_ids.append(user_id)

        if wrong_ids:
            raise IncorrectUserIDError(wrong_ids)

        return tuple(correct_ids)

    def __repr__(self) -> str:
        return (
            f"<PrintContext: allowed_users={self.allowed_users}, "
            f"printer_name={self.printer_name}, "
            f"page_confirm_limit={self.page_confirm_limit}>"
        )


class Settings:
    def __init__(self) -> None:
        self.debug: bool = self._validate_bool("DEBUG")
        self.debug_printer_name = os.getenv("DEBUG_PRINTER_NAME", "PDF")
        self.tg_token: str = self._validate_required_str("TELEGRAM_TOKEN")
        self.print_context: PrintContext = PrintContext(
            os.getenv("PRINTER_NAME") if not self.debug else self.debug_printer_name
        )

    def _validate_bool(self, env_var: str) -> bool:
        val = os.getenv(env_var)
        return bool(val) and val.lower() in ("1", "t", "true", "y", "yes")

    def _validate_required_str(self, env_var: str) -> str:
        """Validates an env var that is required (i.e. there is no default value).

        Args:
            env_var (str): A required environmant variable.

        Raises:
            MissingEnvVarError: Raised if a required env var is missing.

        Returns:
            str: A value of the env var.
        """
        val = os.getenv(env_var)
        if not val:
            raise MissingEnvVarError(env_var)
        return val
