"""Tests for deterministic replay and the deletion workflow."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from audit_ready_memory import (
    DeletionEvent,
    EventStore,
    RetrievalEvent,
    UtteranceEvent,
    replay,
)


def _utterance(content: str, seq: int) -> UtteranceEvent:
    return UtteranceEvent(speaker="user", content=content).model_copy(
        update={"seq": seq}
    )


class TestReplayFunction:
    def test_empty_log(self):
        state = replay([])
        assert state.utterances == ()
        assert state.visible_utterances == ()
        assert state.last_seq is None

    def test_utterances_accumulate_in_order(self):
        a, b = _utterance("a", 0), _utterance("b", 1)
        state = replay([a, b])
        assert state.utterances == (a, b)
        assert state.last_seq == 1

    def test_deletion_hides_target(self):
        a, b = _utterance("a", 0), _utterance("b", 1)
        deletion = DeletionEvent(
            target_event_ids=(a.event_id,), reason="user request"
        ).model_copy(update={"seq": 2})
        state = replay([a, b, deletion])
        assert state.visible_utterances == (b,)
        assert state.is_deleted(a.event_id)
        assert state.deleted[a.event_id] is deletion
        # the log keeps the full history: deletion is a tombstone, not erasure
        assert state.utterances == (a, b)

    def test_retrieval_updates_recall_stats(self):
        a = _utterance("a", 0)
        t1 = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 10, 13, 0, tzinfo=timezone.utc)
        r1 = RetrievalEvent(
            query="q1", retrieved_event_ids=(a.event_id,), timestamp=t1
        ).model_copy(update={"seq": 1})
        r2 = RetrievalEvent(
            query="q2", retrieved_event_ids=(a.event_id,), timestamp=t2
        ).model_copy(update={"seq": 2})
        state = replay([a, r1, r2])
        stats = state.recall_stats[a.event_id]
        assert stats.num_recalled == 2
        assert stats.last_recalled_at == t2

    def test_deterministic(self):
        a, b = _utterance("a", 0), _utterance("b", 1)
        deletion = DeletionEvent(
            target_event_ids=(b.event_id,), reason="r"
        ).model_copy(update={"seq": 2})
        events = [a, b, deletion]
        assert replay(events) == replay(events)

    def test_rejects_unsequenced_event(self):
        with pytest.raises(ValueError):
            replay([UtteranceEvent(speaker="user", content="no seq")])

    def test_rejects_out_of_order(self):
        with pytest.raises(ValueError):
            replay([_utterance("b", 1), _utterance("a", 0)])


class TestStoreReplay:
    def test_replay_from_store(self, tmp_path):
        with EventStore(tmp_path / "db") as store:
            a = store.append(UtteranceEvent(speaker="user", content="keep"))
            b = store.append(UtteranceEvent(speaker="user", content="remove"))
            store.delete((b.event_id,), reason="user request")
            state = store.replay()
            assert state.visible_utterances == (a,)
            assert state.is_deleted(b.event_id)

    def test_replay_at_past_point(self, tmp_path):
        with EventStore(tmp_path / "db") as store:
            a = store.append(UtteranceEvent(speaker="user", content="keep"))
            b = store.append(UtteranceEvent(speaker="user", content="remove"))
            deletion = store.delete((b.event_id,), reason="user request")
            before = store.replay(up_to_seq=deletion.seq - 1)
            assert before.visible_utterances == (a, b)
            after = store.replay(up_to_seq=deletion.seq)
            assert after.visible_utterances == (a,)

    def test_replay_identical_after_reopen(self, tmp_path):
        path = tmp_path / "db"
        with EventStore(path) as store:
            store.append(UtteranceEvent(speaker="user", content="a"))
            b = store.append(UtteranceEvent(speaker="user", content="b"))
            store.delete((b.event_id,), reason="r")
            state_before = store.replay()
        with EventStore(path) as store:
            assert store.replay() == state_before


class TestDeleteWorkflow:
    def test_delete_appends_event(self, tmp_path):
        with EventStore(tmp_path / "db") as store:
            target = store.append(UtteranceEvent(speaker="user", content="secret"))
            deletion = store.delete(
                (target.event_id,), reason="gdpr request", requested_by="user-42"
            )
            assert isinstance(deletion, DeletionEvent)
            assert deletion.seq == 1
            # deletion is visible in the log itself
            assert store.get_event(deletion.event_id) == deletion

    def test_delete_unknown_target_rejected(self, tmp_path):
        with EventStore(tmp_path / "db") as store:
            with pytest.raises(ValueError):
                store.delete((uuid4(),), reason="r")

    def test_delete_non_utterance_rejected(self, tmp_path):
        with EventStore(tmp_path / "db") as store:
            retrieval = store.append(RetrievalEvent(query="q"))
            with pytest.raises(ValueError):
                store.delete((retrieval.event_id,), reason="r")
