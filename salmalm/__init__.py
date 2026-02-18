import logging
import sys

from .constants import LOG_FILE

# Single logger setup — other modules import `from . import log`
log = logging.getLogger('salmalm')
if not log.handlers:
    log.setLevel(logging.INFO)
    log.addHandler(logging.FileHandler(LOG_FILE, encoding='utf-8'))
    log.addHandler(logging.StreamHandler(sys.stdout))
    for h in log.handlers:
        h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
