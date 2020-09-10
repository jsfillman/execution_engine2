import logging
import os
from logging import Logger


def get_logger() -> Logger:
    """
    Get a root logger at INFO level or at LOGLEVEL specified in the environment
    with a a custom set class name and custom formatter.
    # TODO A common scenario is to attach handlers only to the root logger, and to let propagation take care of the rest.
    # But then can we still have custom named loggers?
    :return: EE2 Logger with format created:level:name:msg
    """

    logger = logging.getLogger("ee2")
    if logger.handlers:
        return logger

    logger.propagate = False
    logger.setLevel(0)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    log_level = os.environ.get("LOGLEVEL", "INFO").upper()
    if log_level:
        ch.setLevel(log_level)
        logger.setLevel(log_level)

    formatter = logging.Formatter("%(created)f:%(levelname)s:%(name)s:%(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger
