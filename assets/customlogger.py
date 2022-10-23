import logging

from colorama import Fore


class CustomFormatter(logging.Formatter):
    debug = Fore.LIGHTGREEN_EX
    info = Fore.LIGHTWHITE_EX
    warning = Fore.LIGHTYELLOW_EX
    error = Fore.LIGHTMAGENTA_EX
    crit = Fore.LIGHTRED_EX
    reset = Fore.RESET
    format = "%(asctime)s - %(levelname)s - %(message)s"
    FORMATS = {
        logging.DEBUG: debug + format + reset,
        logging.INFO: info + format + reset,
        logging.WARNING: warning + format + reset,
        logging.ERROR: error + format + reset,
        logging.CRITICAL: crit + format + reset
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
