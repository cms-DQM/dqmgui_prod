import os
import logging
from datetime import datetime
import inspect

logger = logging.getLogger(__name__)
h = logging.StreamHandler()
logger.addHandler(h)
logger.setLevel(logging.INFO)


def logme(msg: str, *args, level=logging.INFO):
    procid = "[%s/%d]" % (inspect.stack()[1].filename.rsplit("/", 1)[-1], os.getpid())
    if "ERROR" in msg:
        level = logging.ERROR
    logger.log(msg=f"{datetime.now()} {procid} " + msg % args, level=level)
