import logging

from bot.settings import LogSettings

log_settings = LogSettings()


def configure_logging(name: str, cfg: LogSettings = log_settings) -> logging.Logger:
    """Logging configuration."""
    logger = logging.getLogger(name)
    logger.setLevel(cfg.log_level)
    formatter = logging.Formatter(fmt=cfg.log_format, datefmt=cfg.log_dt_fmt)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(cfg.log_level)
    logger.addHandler(handler)
    return logger
