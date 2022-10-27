import logging

from colorama import Fore, Back, Style


class CustomFormatter(logging.Formatter):
    debug = Fore.WHITE
    info = Fore.LIGHTWHITE_EX
    warning = Fore.LIGHTMAGENTA_EX
    error = Fore.LIGHTYELLOW_EX
    crit = Fore.LIGHTRED_EX
    reset = Fore.RESET
    format = "%(asctime)s - %(levelname)s - %(message)s"
    FORMATS = {
        logging.DEBUG: Fore.WHITE + format + reset,
        logging.INFO: Fore.LIGHTWHITE_EX + format + reset,
        logging.WARNING: Fore.LIGHTMAGENTA_EX + format + reset,
        logging.ERROR: Fore.LIGHTYELLOW_EX + format + reset,
        logging.CRITICAL: Fore.LIGHTRED_EX + format + reset
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
            fmt="%(asctime)s - %(levelname)s - %(message)s",
            datefmt='%m/%d %I:%M:%S %p'
        )
        return formatter.format(record)


def main():
    logger = logging.getLogger("CustomLogger")
    logger.setLevel(logging.DEBUG)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(CustomFormatter())
    logger.addHandler(ch)

    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")
    logger.critical("critical message")


if __name__ == "__main__":
    main()
