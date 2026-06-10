"""Tests for the ArcadeDB-backed append-only memory."""

from uuid import uuid4

import pytest

from audit_ready_memory import Deletion, Document, Memory, Message, Recall


@pytest.fixture
def memory(tmp_path):
    with Memory(tmp_path / "db") as m:
        yield m


class TestAddMessage:
    def test_assigns_monotonic_seq(self, memory):
        first = memory.add_message(Message(speaker="user", content="one"))
        second = memory.add_message(Message(speaker="user", content="two"))
        assert first.seq == 0
        assert second.seq == 1

    def test_original_event_unchanged(self, memory):
        event = Message(speaker="user", content="hi")
        stored = memory.add_message(event)
        assert event.seq is None
        assert stored.seq == 0
        assert stored.id == event.id

    def test_rejects_already_appended(self, memory):
        stored = memory.add_message(Message(speaker="user", content="hi"))
        with pytest.raises(ValueError):
            memory.add_message(stored)


class TestAddDocument:
    def test_stores_document(self, memory):
        doc = memory.add_document(
            Document(name="report.txt", text="Budget summary", actor="anna")
        )
        assert doc.seq == 0
        assert memory.get(doc.id) == doc

    def test_interleaves_with_messages(self, memory):
        m = memory.add_message(Message(speaker="user", content="hi"))
        d = memory.add_document(Document(name="report.txt", text="text"))
        assert (m.seq, d.seq) == (0, 1)
        assert memory.events() == [m, d]


class TestRecordRecall:
    def test_records_recall(self, memory):
        m = memory.add_message(Message(speaker="user", content="hi"))
        recall = memory.record_recall(Recall(query="greeting", recalled=(m.id,)))
        assert recall.seq == 1

    def test_document_recallable(self, memory):
        d = memory.add_document(Document(name="report.txt", text="text"))
        recall = memory.record_recall(Recall(query="report", recalled=(d.id,)))
        assert recall.recalled == (d.id,)

    def test_unknown_target_rejected(self, memory):
        with pytest.raises(ValueError):
            memory.record_recall(Recall(query="q", recalled=(uuid4(),)))

    def test_non_content_target_rejected(self, memory):
        m = memory.add_message(Message(speaker="user", content="hi"))
        recall = memory.record_recall(Recall(query="q", recalled=(m.id,)))
        with pytest.raises(ValueError):
            memory.record_recall(Recall(query="q2", recalled=(recall.id,)))

    def test_empty_recall_allowed(self, memory):
        recall = memory.record_recall(Recall(query="nothing about cats"))
        assert recall.seq == 0


class TestDelete:
    def test_tombstones_message(self, memory):
        keep = memory.add_message(Message(speaker="user", content="keep"))
        remove = memory.add_message(Message(speaker="user", content="remove"))
        deletion = memory.delete((remove.id,), reason="user request")
        assert isinstance(deletion, Deletion)
        state = memory.replay()
        assert state.visible_messages == (keep,)
        # the deletion itself is visible in the log
        assert memory.get(deletion.id) == deletion
        # and the tombstoned message is still in the log, just not readable
        assert memory.get(remove.id) == remove

    def test_tombstones_document(self, memory):
        d = memory.add_document(Document(name="report.txt", text="text"))
        memory.delete((d.id,), reason="gdpr request", requested_by="anna")
        assert memory.replay().visible_documents == ()

    def test_unknown_target_rejected(self, memory):
        with pytest.raises(ValueError):
            memory.delete((uuid4(),), reason="r")

    def test_non_content_target_rejected(self, memory):
        recall = memory.record_recall(Recall(query="q"))
        with pytest.raises(ValueError):
            memory.delete((recall.id,), reason="r")


class TestLog:
    def test_events_in_log_order(self, memory):
        m = memory.add_message(Message(speaker="user", content="hi"))
        r = memory.record_recall(Recall(query="q", recalled=(m.id,)))
        d = memory.delete((m.id,), reason="cleanup")
        assert memory.events() == [m, r, d]
        assert len(memory) == 3

    def test_filter_by_kind(self, memory):
        memory.add_message(Message(speaker="user", content="hi"))
        r = memory.record_recall(Recall(query="q"))
        assert memory.events(kind="recall") == [r]

    def test_filter_by_session(self, memory):
        a = memory.add_message(
            Message(speaker="user", content="s1 first", session_id="s1")
        )
        memory.add_message(Message(speaker="user", content="s2 only", session_id="s2"))
        b = memory.add_message(
            Message(speaker="user", content="s1 second", session_id="s1")
        )
        assert memory.events(session_id="s1") == [a, b]

    def test_get_missing_returns_none(self, memory):
        assert memory.get(uuid4()) is None


class TestReplay:
    def test_replay_full_state(self, memory):
        a = memory.add_message(Message(speaker="user", content="keep"))
        b = memory.add_message(Message(speaker="user", content="remove"))
        memory.record_recall(Recall(query="q", recalled=(a.id,)))
        memory.delete((b.id,), reason="user request")
        state = memory.replay()
        assert state.visible_messages == (a,)
        assert state.recall_stats[a.id].num_recalled == 1

    def test_replay_at_past_point(self, memory):
        a = memory.add_message(Message(speaker="user", content="keep"))
        b = memory.add_message(Message(speaker="user", content="remove"))
        deletion = memory.delete((b.id,), reason="user request")
        before = memory.replay(up_to_seq=deletion.seq - 1)
        assert before.visible_messages == (a, b)
        after = memory.replay(up_to_seq=deletion.seq)
        assert after.visible_messages == (a,)


class TestPersistence:
    def test_survives_reopen(self, tmp_path):
        path = tmp_path / "db"
        with Memory(path) as memory:
            stored = memory.add_message(Message(speaker="user", content="persist me"))
        with Memory(path) as memory:
            assert memory.get(stored.id) == stored
            assert len(memory) == 1

    def test_seq_continues_after_reopen(self, tmp_path):
        path = tmp_path / "db"
        with Memory(path) as memory:
            memory.add_message(Message(speaker="user", content="first"))
        with Memory(path) as memory:
            second = memory.add_message(Message(speaker="user", content="second"))
            assert second.seq == 1

    def test_replay_identical_after_reopen(self, tmp_path):
        path = tmp_path / "db"
        with Memory(path) as memory:
            memory.add_message(Message(speaker="user", content="a"))
            b = memory.add_message(Message(speaker="user", content="b"))
            memory.delete((b.id,), reason="r")
            state_before = memory.replay()
        with Memory(path) as memory:
            assert memory.replay() == state_before
