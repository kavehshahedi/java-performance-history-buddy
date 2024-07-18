from mhm.utils.colors import ConsoleColors

class Printer:
    def __init__(self) -> None:
        pass

    @staticmethod
    def _print_message(message: str, color: str, num_indentations: int = 0, bold: bool = False) -> None:
        tabs = "\t" * num_indentations
        bold_code = ConsoleColors.BOLD if bold else ''
        print(f"{tabs}{color}{bold_code}{message}{ConsoleColors.ENDC}")

    @staticmethod
    def info(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Printer._print_message(message, ConsoleColors.OKBLUE, num_indentations, bold)

    @staticmethod
    def success(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Printer._print_message(message, ConsoleColors.OKGREEN, num_indentations, bold)

    @staticmethod
    def error(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Printer._print_message(message, ConsoleColors.FAIL, num_indentations, bold)

    @staticmethod
    def warning(message: str, num_indentations: int = 0, bold: bool = False) -> None:
        Printer._print_message(message, ConsoleColors.WARNING, num_indentations, bold)

    @staticmethod
    def separator(num_indentations: int = 0) -> None:
        Printer._print_message('-' * 50, ConsoleColors.OKBLUE, num_indentations)