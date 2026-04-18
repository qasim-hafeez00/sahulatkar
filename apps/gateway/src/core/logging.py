import logging
from pythonjsonlogger import jsonlogger
import sys

def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    while root_logger.hasHandlers():
        root_logger.removeHandler(root_logger.handlers[0])
        
    logHandler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    logHandler.setFormatter(formatter)
    root_logger.addHandler(logHandler)

logger = logging.getLogger("gateway")
