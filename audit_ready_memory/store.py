"""ArcadeDB-backed append-only event store.

The store persists events from :mod:`audit_ready_memory.events` into an
embedded ArcadeDB database. Appends are the only write path: events are
never updated or removed. Deletion of memory content happens by appending
a ``DeletionEvent``; the log itself stays intact.

Each appended event gets a monotonically increasing ``seq`` assigned by
the store, giving the log a total order independent of wall-clock time.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import arcadedb_embedded as arcadedb

from .events import (
    DeletionEvent,
    RetrievalEvent,
    UtteranceEvent,
    event_from_dict,
    event_to_dict,
)
from .replay import MemoryState, replay

_EVENT_TYPE = "MemoryEvent"

ConcreteEvent = UtteranceEvent | RetrievalEvent | DeletionEvent


class EventStore:
    """Append-only event log persisted in an embedded ArcadeDB database.

    Usage::

        with EventStore("./memory-db") as store:
            stored = store.append(UtteranceEvent(speaker="user", content="hi"))
            assert stored.seq == 0
    """

    def __init__(self, path: str | Path):
        path = str(path)
        if arcadedb.database_exists(path):
            self._db = arcadedb.open_database(path)
        else:
            self._db = arcadedb.create_database(path)
            self._init_schema()
        self._next_seq = self._max_seq() + 1

    def _init_schema(self) -> None:
        cmds = [
            f"CREATE DOCUMENT TYPE {_EVENT_TYPE}",
            f"CREATE PROPERTY {_EVENT_TYPE}.event_id STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.seq LONG",
            f"CREATE PROPERTY {_EVENT_TYPE}.kind STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.timestamp STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.session_id STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.payload STRING",
            f"CREATE INDEX ON {_EVENT_TYPE} (event_id) UNIQUE",
            f"CREATE INDEX ON {_EVENT_TYPE} (seq) UNIQUE",
        ]
        for cmd in cmds:
            self._db.command("sql", cmd)

    def _max_seq(self) -> int:
        result = self._db.query(
            "sql", f"SELECT max(seq) AS max_seq FROM {_EVENT_TYPE}"
        ).to_list()
        if not result or result[0].get("max_seq") is None:
            return -1
        return int(result[0]["max_seq"])

    def append(self, event: ConcreteEvent) -> ConcreteEvent:
        """Append an event to the log, assigning its ``seq``.

        Returns a copy of the event with ``seq`` set. Raises ``ValueError``
        if the event already carries a ``seq`` (it was appended before).
        """
        if event.seq is not None:
            raise ValueError(f"event {event.event_id} already has seq={event.seq}")
        stored = event.model_copy(update={"seq": self._next_seq})
        data = event_to_dict(stored)
        with self._db.transaction():
            self._db.command(
                "sql",
                f"INSERT INTO {_EVENT_TYPE} SET "
                "event_id = ?, seq = ?, kind = ?, timestamp = ?, "
                "session_id = ?, payload = ?",
                data["event_id"],
                stored.seq,
                data["kind"],
                data["timestamp"],
                data["session_id"],
                json.dumps(data),
            )
        self._next_seq += 1
        return stored

    def get_event(self, event_id: UUID | str) -> ConcreteEvent | None:
        """Return the event with the given id, or ``None`` if absent."""
        rows = self._db.query(
            "sql",
            f"SELECT payload FROM {_EVENT_TYPE} WHERE event_id = ?",
            str(event_id),
        ).to_list()
        if not rows:
            return None
        return event_from_dict(json.loads(rows[0]["payload"]))

    def list_events(
        self,
        *,
        kind: str | None = None,
        session_id: str | None = None,
        after_seq: int | None = None,
        up_to_seq: int | None = None,
    ) -> list[ConcreteEvent]:
        """Return events in log order (ascending ``seq``), optionally filtered."""
        clauses = []
        params: list[object] = []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if after_seq is not None:
            clauses.append("seq > ?")
            params.append(after_seq)
        if up_to_seq is not None:
            clauses.append("seq <= ?")
            params.append(up_to_seq)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            "sql",
            f"SELECT payload FROM {_EVENT_TYPE}{where} ORDER BY seq ASC",
            *params,
        ).to_list()
        return [event_from_dict(json.loads(row["payload"])) for row in rows]

    def replay(self, *, up_to_seq: int | None = None) -> MemoryState:
        """Reconstruct memory state from the log, optionally at a past point."""
        return replay(self.list_events(up_to_seq=up_to_seq))

    def delete(
        self,
        target_event_ids: tuple[UUID, ...] | list[UUID],
        reason: str,
        *,
        requested_by: str | None = None,
        session_id: str | None = None,
    ) -> DeletionEvent:
        """Append a ``DeletionEvent`` after validating its targets.

        Each target must be an existing utterance in the log. The targets'
        content stays in the log (the log is append-only) but is excluded
        from replayed memory state from this point on.
        """
        for target in target_event_ids:
            existing = self.get_event(target)
            if existing is None:
                raise ValueError(f"cannot delete unknown event {target}")
            if not isinstance(existing, UtteranceEvent):
                raise ValueError(
                    f"cannot delete {existing.kind} event {target}; "
                    "only utterances hold deletable content"
                )
        event = DeletionEvent(
            target_event_ids=tuple(target_event_ids),
            reason=reason,
            requested_by=requested_by,
            session_id=session_id,
        )
        return self.append(event)

    def __len__(self) -> int:
        return self._db.count_type(_EVENT_TYPE)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
