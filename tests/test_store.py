"""Tests for the ArcadeDB-backed append-only event store."""

from uuid import uuid4

import pytest

from audit_ready_memory import (
    DeletionEvent,
    EventStore,
    RetrievalEvent,
    UtteranceEvent,
)


@pytest.fixture
def store(tmp_path):
    with EventStore(tmp_path / "db") as s:
        yield s


class TestAppend:
    def test_assigns_monotonic_seq(self, store):
        first = store.append(UtteranceEvent(speaker="user", content="one"))
        second = store.append(UtteranceEvent(speaker="user", content="two"))
        assert first.seq == 0
        assert second.seq == 1

    def test_original_event_unchanged(self, store):
        event = UtteranceEvent(speaker="user", content="hi")
        stored = store.append(event)
        assert event.seq is None
        assert stored.seq == 0
        assert stored.event_id == event.event_id

    def test_rejects_already_appended(self, store):
        stored = store.append(UtteranceEvent(speaker="user", content="hi"))
        with pytest.raises(ValueError):
            store.append(stored)

    def test_all_event_kinds(self, store):
        utterance = store.append(UtteranceEvent(speaker="user", content="hi"))
        retrieval = store.append(
            RetrievalEvent(query="greeting", retrieved_event_ids=(utterance.event_id,))
        )
        deletion = store.append(
            DeletionEvent(target_event_ids=(utterance.event_id,), reason="test")
        )
        assert [e.seq for e in (utterance, retrieval, deletion)] == [0, 1, 2]
        assert len(store) == 3


class TestGetEvent:
    def test_round_trip(self, store):
        stored = store.append(
            UtteranceEvent(speaker="assistant", content="hello", session_id="s1")
        )
        fetched = store.get_event(stored.event_id)
        assert fetched == stored

    def test_accepts_string_id(self, store):
        stored = store.append(UtteranceEvent(speaker="user", content="hi"))
        assert store.get_event(str(stored.event_id)) == stored

    def test_missing_returns_none(self, store):
        assert store.get_event(uuid4()) is None


class TestListEvents:
    def test_log_order(self, store):
        events = [
            store.append(UtteranceEvent(speaker="user", content=f"msg {i}"))
            for i in range(5)
        ]
        assert store.list_events() == events

    def test_filter_by_kind(self, store):
        store.append(UtteranceEvent(speaker="user", content="hi"))
        retrieval = store.append(RetrievalEvent(query="q"))
        assert store.list_events(kind="retrieval") == [retrieval]

    def test_filter_by_session(self, store):
        in_session = store.append(
            UtteranceEvent(speaker="user", content="hi", session_id="s1")
        )
        store.append(UtteranceEvent(speaker="user", content="bye", session_id="s2"))
        assert store.list_events(session_id="s1") == [in_session]

    def test_after_seq(self, store):
        store.append(UtteranceEvent(speaker="user", content="old"))
        new = store.append(UtteranceEvent(speaker="user", content="new"))
        assert store.list_events(after_seq=0) == [new]

    def test_empty_store(self, store):
        assert store.list_events() == []
        assert len(store) == 0


class TestPersistence:
    def test_survives_reopen(self, tmp_path):
        path = tmp_path / "db"
        with EventStore(path) as store:
            stored = store.append(UtteranceEvent(speaker="user", content="persist me"))
        with EventStore(path) as store:
            assert store.get_event(stored.event_id) == stored
            assert len(store) == 1

    def test_seq_continues_after_reopen(self, tmp_path):
        path = tmp_path / "db"
        with EventStore(path) as store:
            store.append(UtteranceEvent(speaker="user", content="first"))
        with EventStore(path) as store:
            second = store.append(UtteranceEvent(speaker="user", content="second"))
            assert second.seq == 1
