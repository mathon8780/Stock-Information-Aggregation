from __future__ import annotations

import os
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator

from app.config import PROJECT_DIR


class HistoryImportBusy(RuntimeError):
    pass


@contextmanager
def history_import_lock(path: Path | None = None) -> Iterator[None]:
    """CLI、全市场和缺失日线任务共用跨进程锁，进程退出时自动解锁。"""
    path = path or PROJECT_DIR / "data/runtime/full_market_history.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise HistoryImportBusy("已有全市场或缺失日线采集任务运行，请勿重复启动") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def exclusive_history_import(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        with history_import_lock():
            return function(*args, **kwargs)
    return guarded


def history_import_is_running() -> bool:
    try:
        with history_import_lock():
            return False
    except HistoryImportBusy:
        return True
