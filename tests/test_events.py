"""Tests for the event schema."""

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from audit_ready_memory import (
    DeletionEvent,
    Provenance,
    RetrievalEvent,
    UtteranceEvent,
    event_from_dict,
    event_to_dict,
)


class TestUtteranceEvent:
    def test_minimal_creation(self):
        event = UtteranceEvent(speaker="user", content="Hello")
        assert event.kind == "utterance"
        assert event.speaker == "user"
        assert event.content == "Hello"
        assert event.event_id is not None
        assert event.timestamp.tzinfo == timezone.utc
        assert event.seq is None
        assert event.provenance == Provenance()

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            UtteranceEvent(speaker="user", content="")

    def test_empty_speaker_rejected(self):
        with pytest.raises(ValidationError):
            UtteranceEvent(speaker="", content="Hello")

    def test_naive_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            UtteranceEvent(
                speaker="user",
                content="Hello",
                timestamp=datetime(2026, 6, 10, 12, 0, 0),
            )

    def test_timestamp_normalized_to_utc(self):
        cest = timezone(timedelta(hours=2))
        event = UtteranceEvent(
            speaker="user",
            content="Hello",
            timestamp=datetime(2026, 6, 10, 14, 0, 0, tzinfo=cest),
        )
        assert event.timestamp.tzinfo == timezone.utc
        assert event.timestamp.hour == 12

    def test_immutable(self):
        event = UtteranceEvent(speaker="user", content="Hello")
        with pytest.raises(ValidationError):
            event.content = "Changed"

    def test_retain_until(self):
        until = datetime(2027, 1, 1, tzinfo=timezone.utc)
        event = UtteranceEvent(speaker="user", content="Hello", retain_until=until)
        assert event.retain_until == until


class TestRetrievalEvent:
    def test_records_retrieved_ids(self):
        ids = (uuid4(), uuid4())
        event = RetrievalEvent(query="what did the user say?", retrieved_event_ids=ids)
        assert event.kind == "retrieval"
        assert event.retrieved_event_ids == ids

    def test_empty_retrieval_allowed(self):
        event = RetrievalEvent(query="anything about cats?")
        assert event.retrieved_event_ids == ()

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            RetrievalEvent(query="")


class TestDeletionEvent:
    def test_requires_targets(self):
        with pytest.raises(ValidationError):
            DeletionEvent(target_event_ids=(), reason="user request")

    def test_requires_reason(self):
        with pytest.raises(ValidationError):
            DeletionEvent(target_event_ids=(uuid4(),), reason="")

    def test_creation(self):
        target = uuid4()
        event = DeletionEvent(
            target_event_ids=(target,),
            reason="user request",
            requested_by="user-42",
        )
        assert event.kind == "deletion"
        assert event.target_event_ids == (target,)


class TestSerialization:
    @pytest.mark.parametrize(
        "event",
        [
            UtteranceEvent(
                speaker="assistant",
                content="Hi there",
                session_id="s1",
                provenance=Provenance(source="chat", actor="agent-1"),
            ),
            RetrievalEvent(query="greeting", retrieved_event_ids=(uuid4(),)),
            DeletionEvent(target_event_ids=(uuid4(),), reason="gdpr request"),
        ],
    )
    def test_round_trip(self, event):
        data = event_to_dict(event)
        restored = event_from_dict(data)
        assert restored == event

    def test_kind_discriminates(self):
        data = event_to_dict(UtteranceEvent(speaker="user", content="Hello"))
        restored = event_from_dict(data)
        assert isinstance(restored, UtteranceEvent)

    def test_unknown_kind_rejected(self):
        data = event_to_dict(UtteranceEvent(speaker="user", content="Hello"))
        data["kind"] = "mystery"
        with pytest.raises(ValidationError):
            event_from_dict(data)
