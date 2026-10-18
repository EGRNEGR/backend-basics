import contextvars
import logging
import uuid

_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")


class RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _run_id.get()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RunIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s run_id=%(run_id)s %(name)s: %(message)s"
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def set_run_id() -> str:
    run_id = uuid.uuid4().hex[:8]
    _run_id.set(run_id)
    return run_id
