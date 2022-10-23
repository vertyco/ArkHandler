import logging

import colorama
from colorama import Fore, Back, Style

colorama.init(autoreset=True)


class CustomFormatter(logging.Formatter):
    bright = Style.BRIGHT
    debug = Fore.LIGHTGREEN_EX
    info = Fore.LIGHTWHITE_EX
    warning = Fore.LIGHTYELLOW_EX
    error = Fore.LIGHTMAGENTA_EX
    crit = Fore.LIGHTRED_EX
    critback = Back.LIGHTYELLOW_EX
    fmt = "%(asctime)s - %(levelname)s - %(message)s"
    FORMATS = {
        logging.DEBUG: bright + debug + fmt,
        logging.INFO: bright + info + fmt,
        logging.WARNING: bright + warning + fmt,
        logging.ERROR: bright + error + fmt,
        logging.CRITICAL: critback + bright + crit + fmt
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(
            fmt=log_fmt,
            datefmt='%m/%d %I:%M:%S %p'
        )
        return formatter.format(record)


class StandardFormatter(logging.Formatter):
    def format(self, record):
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)",
            datefmt='%m/%d %I:%M:%S %p'
        )
        return formatter.format(record)


def main():
    logger = logging.getLogger("CustomLogger")
    logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(CustomFormatter())
    logger.addHandler(console)

    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")
    logger.critical("critical message")


if __name__ == "__main__":
    main()
