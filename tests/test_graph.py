"""Tests for the graph layout of the log and for read-only Cypher queries."""

import arcadedb
import pytest

from audit_ready_memory import Document, Memory, Message


@pytest.fixture
def memory(tmp_path):
    with Memory(tmp_path / "db") as m:
        yield m


def _say(memory, content, session_id=None):
    return memory.add_message(
        Message(speaker="anna", content=content, session_id=session_id)
    )


def _pairs(memory, edge):
    rows = memory.query(
        f"MATCH (a:MemoryEvent)-[:{edge}]->(b:MemoryEvent) "
        "RETURN a.seq AS source, b.seq AS target ORDER BY source, target"
    )
    return [(row["source"], row["target"]) for row in rows]


class TestNodes:
    def test_one_labelled_node_per_event(self, memory):
        message = _say(memory, "hi")
        memory.add_document(Document(name="a.txt", text="a"))
        memory.recall("hi")
        memory.delete((message.id,), reason="r")
        for seq, label in enumerate(("Message", "Document", "Recall", "Deletion")):
            rows = memory.query(f"MATCH (n:{label}) RETURN n.seq AS seq")
            assert [row["seq"] for row in rows] == [seq]
        assert len(memory) == 4

    def test_seq_is_unique_across_kinds(self, memory):
        _say(memory, "hi")
        memory._next_seq = 0
        with pytest.raises(Exception, match="Duplicated"):
            memory.add_document(Document(name="a.txt", text="a"))
        assert len(memory) == 1


class TestNext:
    def test_chains_messages_per_session(self, memory):
        _say(memory, "a1", "a")
        _say(memory, "b1", "b")
        memory.add_document(Document(name="a.txt", text="a", session_id="a"))
        _say(memory, "a2", "a")
        _say(memory, "b2", "b")
        _say(memory, "a3", "a")
        assert _pairs(memory, "NEXT") == [(0, 3), (1, 4), (3, 5)]

    def test_messages_without_session_form_one_chain(self, memory):
        _say(memory, "one")
        _say(memory, "other", "a")
        _say(memory, "two")
        assert _pairs(memory, "NEXT") == [(0, 2)]

    def test_chain_continues_after_reopen(self, tmp_path):
        path = tmp_path / "db"
        with Memory(path) as memory:
            _say(memory, "one", "a")
        with Memory(path) as memory:
            _say(memory, "two", "a")
            assert _pairs(memory, "NEXT") == [(0, 1)]


class TestRecalledAndDeleted:
    def test_recall_links_to_what_it_read(self, memory):
        pump = _say(memory, "pump failed")
        _say(memory, "lunch")
        recall, _ = memory.recall("pump")
        rows = memory.query(
            "MATCH (r:Recall)-[:RECALLED]->(m:MemoryEvent {id: $id}) "
            "RETURN r.seq AS seq",
            {"id": str(pump.id)},
        )
        assert [row["seq"] for row in rows] == [recall.seq]
        assert _pairs(memory, "RECALLED") == [(2, 0)]

    def test_deletion_links_once_per_target(self, memory):
        a = _say(memory, "a")
        b = _say(memory, "b")
        memory.delete((a.id, b.id, a.id), reason="r")
        assert _pairs(memory, "DELETED") == [(2, 0), (2, 1)]

    def test_expiry_is_linked_too(self, memory):
        from datetime import datetime, timezone

        memory.add_message(
            Message(
                speaker="anna",
                content="old",
                retain_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
        memory.expire()
        assert _pairs(memory, "DELETED") == [(1, 0)]

    def test_rejected_write_leaves_no_edges(self, memory):
        from uuid import uuid4

        a = _say(memory, "a")
        with pytest.raises(ValueError):
            memory.delete((a.id, uuid4()), reason="r")
        assert _pairs(memory, "DELETED") == []


class TestQueryIsReadOnly:
    @pytest.mark.parametrize(
        "cypher",
        [
            "MATCH (m:Message) DETACH DELETE m",
            "MATCH (m:Message) SET m.payload = 'x'",
            "CREATE (:Message {id: 'z', seq: 99})",
        ],
    )
    def test_writes_are_refused(self, memory, cypher):
        stored = _say(memory, "keep")
        with pytest.raises(Exception):
            memory.query(cypher)
        assert memory.events() == [stored]


class TestOldLayout:
    def test_flat_database_is_refused(self, tmp_path):
        path = str(tmp_path / "old")
        db = arcadedb.create_database(path)
        db.command("sql", "CREATE DOCUMENT TYPE MemoryEvent")
        db.close()
        with pytest.raises(ValueError, match="older layout"):
            Memory(path)
