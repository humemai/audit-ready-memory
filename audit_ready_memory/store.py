"""ArcadeDB-backed append-only memory.

``Memory`` persists events from :mod:`audit_ready_memory.events` into an
embedded ArcadeDB database. Appends are the only write path: events are
never updated or removed. Deletion of memory content happens by appending
a ``Deletion`` event; the log itself stays intact.

Each appended event gets a monotonically increasing ``seq`` assigned by
the store, giving the log a total order independent of wall-clock time.

The log is stored as a graph. Every event is a node, labelled ``Message``,
``Document``, ``Recall``, or ``Deletion``. ``NEXT`` links consecutive messages
of a session, ``RECALLED`` links a recall to what it read, and ``DELETED``
links a deletion to what it removed. The edges are written in the same
transaction as their event. Replay reads only the events and their ``seq``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import arcadedb

from .events import (
    Deletion,
    Document,
    Message,
    Recall,
    event_from_dict,
    event_to_dict,
)
from .replay import MemoryState, replay
from .retrieval import search

_EVENT_TYPE = "MemoryEvent"
_NODE_TYPES = {
    "message": "Message",
    "document": "Document",
    "recall": "Recall",
    "deletion": "Deletion",
}
_EDGE_TYPES = ("NEXT", "RECALLED", "DELETED")

ConcreteEvent = Message | Document | Recall | Deletion


class Memory:
    """Append-only memory log persisted in an embedded ArcadeDB database.

    Usage::

        with Memory("./memory-db") as memory:
            m = memory.add_message(Message(speaker="anna", content="hi"))
            d = memory.add_document(Document(name="report.txt", text="..."))
            memory.record_recall(Recall(query="report", recalled=(d.id,)))
            memory.delete((m.id,), reason="user request")
    """

    def __init__(self, path: str | Path):
        path = str(path)
        if arcadedb.database_exists(path):
            self._db = arcadedb.open_database(path)
            self._require_graph_layout(path)
        else:
            self._db = arcadedb.create_database(path)
            self._init_schema()
        self._next_seq = self._max_seq() + 1
        # last message id per session, filled in as sessions are written to
        self._last_message: dict[str | None, str | None] = {}

    def _require_graph_layout(self, path: str) -> None:
        rows = self._db.query(
            "sql", "SELECT type FROM schema:types WHERE name = ?", _EVENT_TYPE
        ).to_list()
        if not rows or rows[0]["type"] != "vertex":
            self._db.close()
            raise ValueError(
                f"{path} is not a graph memory database; databases written by "
                "audit-ready-memory 0.0.2 or earlier use an older layout"
            )

    def _init_schema(self) -> None:
        cmds = [
            f"CREATE VERTEX TYPE {_EVENT_TYPE}",
            f"CREATE PROPERTY {_EVENT_TYPE}.id STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.seq LONG",
            f"CREATE PROPERTY {_EVENT_TYPE}.kind STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.timestamp STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.session_id STRING",
            f"CREATE PROPERTY {_EVENT_TYPE}.payload STRING",
            f"CREATE INDEX ON {_EVENT_TYPE} (id) UNIQUE",
            f"CREATE INDEX ON {_EVENT_TYPE} (seq) UNIQUE",
            *(
                f"CREATE VERTEX TYPE {name} EXTENDS {_EVENT_TYPE}"
                for name in _NODE_TYPES.values()
            ),
            *(f"CREATE EDGE TYPE {name}" for name in _EDGE_TYPES),
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

    def _append(self, event: ConcreteEvent) -> ConcreteEvent:
        if event.seq is not None:
            raise ValueError(f"event {event.id} already has seq={event.seq}")
        stored = event.model_copy(update={"seq": self._next_seq})
        data = event_to_dict(stored)
        previous = None
        if isinstance(stored, Message):
            previous = self._last_message_id(stored.session_id)
        with self._db.transaction():
            self._db.command(
                "sql",
                f"INSERT INTO {_NODE_TYPES[stored.kind]} SET "
                "id = ?, seq = ?, kind = ?, timestamp = ?, "
                "session_id = ?, payload = ?",
                data["id"],
                stored.seq,
                data["kind"],
                data["timestamp"],
                data["session_id"],
                json.dumps(data),
            )
            if previous is not None:
                self._link("NEXT", previous, data["id"])
            if isinstance(stored, Recall):
                for target in dict.fromkeys(stored.recalled):
                    self._link("RECALLED", data["id"], str(target))
            elif isinstance(stored, Deletion):
                for target in dict.fromkeys(stored.targets):
                    self._link("DELETED", data["id"], str(target))
        self._next_seq += 1
        if isinstance(stored, Message):
            self._last_message[stored.session_id] = data["id"]
        return stored

    def _last_message_id(self, session_id: str | None) -> str | None:
        if session_id not in self._last_message:
            clause = "session_id IS NULL" if session_id is None else "session_id = ?"
            params = () if session_id is None else (session_id,)
            rows = self._db.query(
                "sql",
                f"SELECT id, seq FROM Message WHERE {clause} "
                "ORDER BY seq DESC LIMIT 1",
                *params,
            ).to_list()
            self._last_message[session_id] = rows[0]["id"] if rows else None
        return self._last_message[session_id]

    def _link(self, edge: str, source: str, target: str) -> None:
        self._db.command(
            "sql",
            f"CREATE EDGE {edge} "
            f"FROM (SELECT FROM {_EVENT_TYPE} WHERE id = ?) "
            f"TO (SELECT FROM {_EVENT_TYPE} WHERE id = ?)",
            source,
            target,
        )

    def _require_content_event(self, event_id: UUID, action: str) -> None:
        existing = self.get(event_id)
        if existing is None:
            raise ValueError(f"cannot {action} unknown event {event_id}")
        if not isinstance(existing, (Message, Document)):
            raise ValueError(
                f"cannot {action} {existing.kind} event {event_id}; "
                "only messages and documents hold memory content"
            )

    def add_message(self, message: Message) -> Message:
        """Append a conversational turn (episodic memory)."""
        return self._append(message)

    def add_document(self, document: Document) -> Document:
        """Append an uploaded document (semantic memory)."""
        return self._append(document)

    def record_recall(self, recall: Recall) -> Recall:
        """Append a read: which memories entered the AI's context.

        Each recalled id must reference an existing message or document.
        """
        for target in recall.recalled:
            self._require_content_event(target, "recall")
        return self._append(recall)

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        session_id: str | None = None,
        source: str = "unknown",
        actor: str | None = None,
    ) -> tuple[Recall, list[Message | Document]]:
        """Search visible memory and append a matching ``Recall`` event.

        The returned events are exactly the set recorded in the audit log;
        retrieval and its audit record cannot diverge. Content whose
        ``retain_until`` has passed at the time of the recall is left out,
        whether or not :meth:`expire` has run.
        """
        now = datetime.now(timezone.utc)
        items = search(self.replay(), query, limit=limit, as_of=now)
        recall = self.record_recall(
            Recall(
                timestamp=now,
                query=query,
                recalled=tuple(item.id for item in items),
                session_id=session_id,
                source=source,
                actor=actor,
            )
        )
        return recall, items

    def delete(
        self,
        targets: tuple[UUID, ...] | list[UUID],
        reason: str,
        *,
        requested_by: str | None = None,
        session_id: str | None = None,
    ) -> Deletion:
        """Append a ``Deletion`` event after validating its targets.

        Each target must be an existing message or document. The targets'
        content stays in the log (the log is append-only) but is excluded
        from replayed memory state from this point on.
        """
        for target in targets:
            self._require_content_event(target, "delete")
        event = Deletion(
            targets=tuple(targets),
            reason=reason,
            requested_by=requested_by,
            session_id=session_id,
        )
        return self._append(event)

    def expire(
        self,
        *,
        as_of: datetime | None = None,
        requested_by: str | None = None,
        session_id: str | None = None,
    ) -> Deletion | None:
        """Delete everything whose retention has run out, as one ``Deletion``.

        ``as_of`` defaults to now. It must carry a timezone and may not be in
        the future, because a deletion cannot be undone. Returns ``None``, and
        writes nothing, if nothing has expired.
        """
        now = datetime.now(timezone.utc)
        as_of = as_of or now
        expired = self.replay().expired(as_of)
        if as_of > now:
            raise ValueError(f"as_of {as_of.isoformat()} is in the future")
        if not expired:
            return None
        return self.delete(
            tuple(item.id for item in expired),
            reason=f"retention period elapsed (as of {as_of.isoformat()})",
            requested_by=requested_by,
            session_id=session_id,
        )

    def get(self, event_id: UUID | str) -> ConcreteEvent | None:
        """Return the event with the given id, or ``None`` if absent."""
        rows = self._db.query(
            "sql",
            f"SELECT payload FROM {_EVENT_TYPE} WHERE id = ?",
            str(event_id),
        ).to_list()
        if not rows:
            return None
        return event_from_dict(json.loads(rows[0]["payload"]))

    def events(
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

    def query(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        """Run a read-only Cypher query over the memory graph.

        A query that would write raises an error from the database, so the log
        stays append-only. This is an audit view: it also returns deleted and
        expired content. Do not put its results into a model's context; use
        :meth:`recall` for that.
        """
        args = () if parameters is None else (parameters,)
        return self._db.query("opencypher", cypher, *args).to_list()

    def replay(self, *, up_to_seq: int | None = None) -> MemoryState:
        """Reconstruct memory state from the log, optionally at a past point."""
        return replay(self.events(up_to_seq=up_to_seq))

    def __len__(self) -> int:
        return self._db.count_type(_EVENT_TYPE)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Memory:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
