import logging
import sys

def setup_logging(env: str = "production") -> None:
    level = logging.INFO if env == "production" else logging.DEBUG
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Never log secrets. Anything passing through these loggers must already be redacted.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
