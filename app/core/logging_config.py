import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_level: str = "INFO") -> None:
    """콘솔 + 파일 핸들러를 루트 로거에 등록합니다.

    - 콘솔: LOG_LEVEL 이상만 출력
    - 파일:  logs/app.log, DEBUG 이상 전체 기록, 10 MB 회전, 최대 5개 보관
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # 외부 라이브러리 노이즈 억제
    for noisy in ("httpx", "httpcore", "neo4j", "uvicorn.access", "google.auth", "google.api_core"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
