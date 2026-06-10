"""Tests for deterministic replay (pure fold over event lists)."""

from datetime import datetime, timezone

import pytest

from audit_ready_memory import Deletion, Document, Message, Recall, replay


def _message(content: str, seq: int) -> Message:
    return Message(speaker="user", content=content).model_copy(update={"seq": seq})


def _document(name: str, seq: int) -> Document:
    return Document(name=name, text=f"text of {name}").model_copy(update={"seq": seq})


class TestReplayFunction:
    def test_empty_log(self):
        state = replay([])
        assert state.messages == ()
        assert state.documents == ()
        assert state.visible_messages == ()
        assert state.last_seq is None

    def test_messages_accumulate_in_order(self):
        a, b = _message("a", 0), _message("b", 1)
        state = replay([a, b])
        assert state.messages == (a, b)
        assert state.last_seq == 1

    def test_documents_accumulate(self):
        m = _message("hi", 0)
        d = _document("report.txt", 1)
        state = replay([m, d])
        assert state.documents == (d,)
        assert state.visible_documents == (d,)

    def test_deletion_hides_message(self):
        a, b = _message("a", 0), _message("b", 1)
        deletion = Deletion(targets=(a.id,), reason="user request").model_copy(
            update={"seq": 2}
        )
        state = replay([a, b, deletion])
        assert state.visible_messages == (b,)
        assert state.is_deleted(a.id)
        assert state.deleted[a.id] is deletion
        # the log keeps the full history: deletion is a tombstone, not erasure
        assert state.messages == (a, b)

    def test_deletion_hides_document(self):
        d = _document("report.txt", 0)
        deletion = Deletion(targets=(d.id,), reason="gdpr request").model_copy(
            update={"seq": 1}
        )
        state = replay([d, deletion])
        assert state.visible_documents == ()
        assert state.documents == (d,)

    def test_recall_updates_stats(self):
        a = _message("a", 0)
        t1 = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 10, 13, 0, tzinfo=timezone.utc)
        r1 = Recall(query="q1", recalled=(a.id,), timestamp=t1).model_copy(
            update={"seq": 1}
        )
        r2 = Recall(query="q2", recalled=(a.id,), timestamp=t2).model_copy(
            update={"seq": 2}
        )
        state = replay([a, r1, r2])
        stats = state.recall_stats[a.id]
        assert stats.num_recalled == 2
        assert stats.last_recalled_at == t2

    def test_deterministic(self):
        a, b = _message("a", 0), _message("b", 1)
        deletion = Deletion(targets=(b.id,), reason="r").model_copy(update={"seq": 2})
        events = [a, b, deletion]
        assert replay(events) == replay(events)

    def test_rejects_unsequenced_event(self):
        with pytest.raises(ValueError):
            replay([Message(speaker="user", content="no seq")])

    def test_rejects_out_of_order(self):
        with pytest.raises(ValueError):
            replay([_message("b", 1), _message("a", 0)])
