from loguru import logger
import sys


class Logger:
    logger.remove()
    logger.add(sys.stdout, colorize=True, format="{message}")

    def __init__(self) -> None:
        pass

    @staticmethod
    def _log_message(message: str, color: str, num_indentations: int = 0, bold: bool = False) -> None:
        tabs = "\t" * num_indentations
        message = f"{tabs}<{color}>{message}</{color}>"
        if bold:
            message = f"<bold>{message}</bold>"
        logger.opt(colors=True).info(message)

    @staticmethod
    def info(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Logger._log_message(message, "blue", num_indentations, bold)

    @staticmethod
    def success(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Logger._log_message(message, "green", num_indentations, bold)

    @staticmethod
    def error(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Logger._log_message(message, "red", num_indentations, bold)

    @staticmethod
    def warning(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Logger._log_message(message, "yellow", num_indentations, bold)

    @staticmethod
    def separator(num_indentations: int = 0) -> None:
        Logger._log_message('-' * 50, "blue", num_indentations)