import logging
from logging import handlers

import colorama
from colorama import Back, Fore, Style


class PrettyFormatter(logging.Formatter):
    colorama.init(autoreset=True)
    fmt = "%(asctime)s - %(levelname)s - %(message)s"
    formats = {
        logging.DEBUG: Fore.LIGHTGREEN_EX + Style.BRIGHT + fmt,
        logging.INFO: Fore.LIGHTWHITE_EX + Style.BRIGHT + fmt,
        logging.WARNING: Fore.YELLOW + Style.BRIGHT + fmt,
        logging.ERROR: Fore.LIGHTMAGENTA_EX + Style.BRIGHT + fmt,
        logging.CRITICAL: Fore.LIGHTYELLOW_EX + Back.RED + Style.BRIGHT + fmt,
    }

    def format(self, record):
        log_fmt = self.formats.get(record.levelno)
        formatter = logging.Formatter(fmt=log_fmt, datefmt="%m/%d %I:%M:%S %p")
        return formatter.format(record)


class StandardFormatter(logging.Formatter):
    def format(self, record):
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%m/%d %I:%M:%S %p"
        )
        return formatter.format(record)


# Log setup
log = logging.getLogger(__file__)
log.setLevel(logging.DEBUG)
# Console logs
console = logging.StreamHandler()
console.setFormatter(PrettyFormatter())
# File logs
logfile = handlers.RotatingFileHandler(
    "logs.log", mode="a", maxBytes=5 * 1024 * 1024, backupCount=3
)
logfile.setFormatter(StandardFormatter())
# Add handlers
log.addHandler(console)
log.addHandler(logfile)
