"""
Structured JSON logging for the payment orchestrator.
Produces ELK / CloudWatch compatible output.
"""
import logging
import sys

from pythonjsonlogger.jsonlogger import JsonFormatter


def setup_logging(service_name: str, log_level: str = "INFO") -> None:
    root = logging.getLogger()
    # Remove any existing handlers to prevent duplicate output
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
        },
        static_fields={"service": service_name},
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
