"""What the demo adds around the library: one private memory per account, limits, and deletion.

Nothing here imports Streamlit, so it can be tested on its own.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from audit_ready_memory import Document, Memory, Message

LOCAL_ACCOUNT = "local"
SCENARIO_DIR = Path(__file__).parent / "scenarios"


@dataclass(frozen=True)
class Settings:
    """Read from the environment. The defaults suit a local run."""

    hosted: bool
    data_dir: Path
    model: str
    replies_per_account: int
    replies_total: int
    max_events: int
    max_document_chars: int
    max_upload_kb: int
    max_reply_tokens: int
    idle_close_minutes: int
    keep_days: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        hosted = env.get("ARM_DEMO_HOSTED") == "1"
        data_dir = env.get("ARM_DEMO_DATA")
        if hosted and not data_dir:
            raise RuntimeError("set ARM_DEMO_DATA to the folder that keeps the memories")

        def number(name: str, default: int) -> int:
            return int(env.get(name, default))

        return cls(
            hosted=hosted,
            data_dir=Path(data_dir) if data_dir else Path(__file__).parent / "data",
            model=env.get("ARM_DEMO_MODEL", "qwen/qwen3.8-flash"),
            replies_per_account=number("ARM_DEMO_REPLIES_PER_ACCOUNT", 30),
            replies_total=number("ARM_DEMO_REPLIES_TOTAL", 500),
            max_events=number("ARM_DEMO_MAX_EVENTS", 1000),
            max_document_chars=number("ARM_DEMO_MAX_DOCUMENT_CHARS", 20_000),
            max_upload_kb=number("ARM_DEMO_MAX_UPLOAD_KB", 200),
            max_reply_tokens=number("ARM_DEMO_MAX_REPLY_TOKENS", 600),
            idle_close_minutes=number("ARM_DEMO_IDLE_CLOSE_MINUTES", 30),
            keep_days=number("ARM_DEMO_KEEP_DAYS", 90),
        )


def account_key(issuer: str, subject: str) -> str:
    """The folder name for an account: a hash, so no identifier is written to disk."""
    if not subject:
        raise ValueError("the sign-in gave no account identifier")
    return hashlib.sha256(f"{issuer}\n{subject}".encode()).hexdigest()[:32]


class _Space:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.memory: Memory | None = None
        self.last_used = 0.0


class Spaces:
    """One memory database per account, opened on demand and closed when idle.

    A :class:`Memory` allows one writer, so each account's memory is used by one
    thread at a time. Different accounts do not wait for each other.
    """

    def __init__(
        self,
        root: Path,
        *,
        idle_close_seconds: float,
        keep_days: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._idle = idle_close_seconds
        self._keep_seconds = keep_days * 86_400
        self._clock = clock
        self._guard = threading.Lock()
        self._spaces: dict[str, _Space] = {}
        self._purged_on = 0.0
        # a restart or a deploy stops the server; leave no database open behind it
        atexit.register(self.close)

    def _folder(self, key: str) -> Path:
        if not key.isalnum():
            raise ValueError("an account key holds letters and digits only")
        return self.root / "spaces" / key

    @contextmanager
    def _locked(self, key: str):
        while True:
            with self._guard:
                space = self._spaces.setdefault(key, _Space())
            space.lock.acquire()
            # it may have been removed while this thread waited for it
            if self._spaces.get(key) is space:
                break
            space.lock.release()
        try:
            yield space
        finally:
            space.lock.release()

    @contextmanager
    def use(self, key: str):
        """The account's memory, held for the duration of the block."""
        self.tidy()
        with self._locked(key) as space:
            folder = self._folder(key)
            if space.memory is None:
                folder.mkdir(parents=True, exist_ok=True)
                space.memory = Memory(folder / "db")
            stamp = folder / "last-seen"
            stamp.touch()
            os.utime(stamp, (self._clock(), self._clock()))
            try:
                yield space.memory
            finally:
                space.last_used = self._clock()

    def delete(self, key: str) -> None:
        """Remove the account's database from disk. This cannot be undone."""
        with self._locked(key) as space:
            if space.memory is not None:
                space.memory.close()
                space.memory = None
            folder = self._folder(key)
            if folder.exists():
                shutil.rmtree(folder)
            with self._guard:
                self._spaces.pop(key, None)

    def tidy(self) -> None:
        """Close idle databases, and once a day delete those past their keep time."""
        self.close_idle()
        if self._clock() - self._purged_on >= 86_400:
            self._purged_on = self._clock()
            self.purge_stale()

    def close_idle(self) -> list[str]:
        closed = []
        with self._guard:
            candidates = list(self._spaces.items())
        for key, space in candidates:
            if not space.lock.acquire(blocking=False):
                continue  # in use right now
            try:
                idle = self._clock() - space.last_used >= self._idle
                if space.memory is not None and idle:
                    space.memory.close()
                    space.memory = None
                    closed.append(key)
            finally:
                space.lock.release()
        return closed

    def purge_stale(self) -> list[str]:
        """Delete memories nobody has visited for the keep time."""
        removed = []
        for folder in sorted((self.root / "spaces").glob("*")):
            stamp = folder / "last-seen"
            seen = (stamp if stamp.exists() else folder).stat().st_mtime
            if self._clock() - seen > self._keep_seconds:
                self.delete(folder.name)
                removed.append(folder.name)
        return removed

    def is_open(self, key: str) -> bool:
        space = self._spaces.get(key)
        return space is not None and space.memory is not None

    def close(self) -> None:
        for space in list(self._spaces.values()):
            with space.lock:
                if space.memory is not None:
                    space.memory.close()
                    space.memory = None


class Usage:
    """AI replies used today, per account and in total. Resets at midnight UTC."""

    def __init__(
        self,
        path: Path,
        *,
        per_account: int,
        total: int,
        today: Callable[[], date] = lambda: datetime.now(timezone.utc).date(),
    ) -> None:
        self.path = Path(path)
        self.per_account = per_account
        self.total = total
        self._today = today
        self._lock = threading.Lock()

    def _load(self) -> dict:
        day = self._today().isoformat()
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if data.get("date") == day:
                return data
        return {"date": day, "total": 0, "accounts": {}}

    def remaining(self, key: str) -> int:
        with self._lock:
            data = self._load()
        mine = self.per_account - data["accounts"].get(key, 0)
        return max(0, min(mine, self.total - data["total"]))

    def take(self, key: str) -> bool:
        """Count one reply. ``False``, and nothing counted, if a limit is reached."""
        with self._lock:
            data = self._load()
            used = data["accounts"].get(key, 0)
            if used >= self.per_account or data["total"] >= self.total:
                return False
            data["accounts"][key] = used + 1
            data["total"] += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            draft = self.path.with_suffix(".new")
            draft.write_text(json.dumps(data))
            draft.replace(self.path)
            return True


def capped_client(client, *, max_tokens: int):
    """Wrap an OpenAI-compatible client so that every reply is short and cheap.

    Reasoning is switched off with OpenRouter's ``reasoning`` field, because it is
    billed like output and a demo reply does not need it.
    """

    def create(*, model, messages):
        return client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            extra_body={"reasoning": {"enabled": False}},
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def scenarios() -> dict[str, dict]:
    """The example data sets, by title. Adding a file adds a scenario."""
    found = {}
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        found[scenario["title"]] = scenario
    return found


def load_scenario(memory: Memory, scenario: dict, *, now: datetime | None = None) -> int:
    """Append a scenario's events to the memory and return how many there were."""
    now = now or datetime.now(timezone.utc)
    for item in scenario["events"]:
        if item["type"] == "recall":
            memory.recall(item["query"], source="example")
            continue
        keep = item.get("keep_minutes")
        until = None if keep is None else now + timedelta(minutes=keep)
        if item["type"] == "message":
            memory.add_message(
                Message(
                    speaker=item["speaker"],
                    content=item["text"],
                    retain_until=until,
                    source="example",
                )
            )
        else:
            memory.add_document(
                Document(
                    name=item["name"],
                    text=item["text"],
                    actor=item.get("speaker"),
                    retain_until=until,
                    source="example",
                )
            )
    return len(scenario["events"])
