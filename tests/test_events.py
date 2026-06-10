"""Tests for the event schema."""

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from audit_ready_memory import (
    Deletion,
    Document,
    Message,
    Recall,
    event_from_dict,
    event_to_dict,
)


class TestMessage:
    def test_minimal_creation(self):
        event = Message(speaker="user", content="Hello")
        assert event.kind == "message"
        assert event.speaker == "user"
        assert event.content == "Hello"
        assert event.id is not None
        assert event.timestamp.tzinfo == timezone.utc
        assert event.seq is None
        assert event.source == "unknown"
        assert event.actor is None

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            Message(speaker="user", content="")

    def test_empty_speaker_rejected(self):
        with pytest.raises(ValidationError):
            Message(speaker="", content="Hello")

    def test_naive_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            Message(
                speaker="user",
                content="Hello",
                timestamp=datetime(2026, 6, 10, 12, 0, 0),
            )

    def test_timestamp_normalized_to_utc(self):
        cest = timezone(timedelta(hours=2))
        event = Message(
            speaker="user",
            content="Hello",
            timestamp=datetime(2026, 6, 10, 14, 0, 0, tzinfo=cest),
        )
        assert event.timestamp.tzinfo == timezone.utc
        assert event.timestamp.hour == 12

    def test_immutable(self):
        event = Message(speaker="user", content="Hello")
        with pytest.raises(ValidationError):
            event.content = "Changed"

    def test_retain_until(self):
        until = datetime(2027, 1, 1, tzinfo=timezone.utc)
        event = Message(speaker="user", content="Hello", retain_until=until)
        assert event.retain_until == until


class TestDocument:
    def test_minimal_creation(self):
        event = Document(name="report.txt", text="Budget summary")
        assert event.kind == "document"
        assert event.name == "report.txt"
        assert event.text == "Budget summary"
        assert event.media_type == "text/plain"
        assert event.sha256 is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            Document(name="", text="content")

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            Document(name="report.txt", text="")

    def test_with_metadata(self):
        event = Document(
            name="report.pdf",
            media_type="application/pdf",
            text="extracted text",
            sha256="a" * 64,
            actor="anna",
        )
        assert event.media_type == "application/pdf"
        assert event.sha256 == "a" * 64
        assert event.actor == "anna"


class TestRecall:
    def test_records_recalled_ids(self):
        ids = (uuid4(), uuid4())
        event = Recall(query="what did the user say?", recalled=ids)
        assert event.kind == "recall"
        assert event.recalled == ids

    def test_empty_recall_allowed(self):
        event = Recall(query="anything about cats?")
        assert event.recalled == ()

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            Recall(query="")


class TestDeletion:
    def test_requires_targets(self):
        with pytest.raises(ValidationError):
            Deletion(targets=(), reason="user request")

    def test_requires_reason(self):
        with pytest.raises(ValidationError):
            Deletion(targets=(uuid4(),), reason="")

    def test_creation(self):
        target = uuid4()
        event = Deletion(
            targets=(target,),
            reason="user request",
            requested_by="user-42",
        )
        assert event.kind == "deletion"
        assert event.targets == (target,)


class TestSerialization:
    @pytest.mark.parametrize(
        "event",
        [
            Message(
                speaker="assistant",
                content="Hi there",
                session_id="s1",
                source="chat",
                actor="agent-1",
            ),
            Document(name="report.txt", text="Budget summary", actor="anna"),
            Recall(query="greeting", recalled=(uuid4(),)),
            Deletion(targets=(uuid4(),), reason="gdpr request"),
        ],
    )
    def test_round_trip(self, event):
        data = event_to_dict(event)
        restored = event_from_dict(data)
        assert restored == event

    def test_kind_discriminates(self):
        data = event_to_dict(Message(speaker="user", content="Hello"))
        restored = event_from_dict(data)
        assert isinstance(restored, Message)

    def test_unknown_kind_rejected(self):
        data = event_to_dict(Message(speaker="user", content="Hello"))
        data["kind"] = "mystery"
        with pytest.raises(ValidationError):
            event_from_dict(data)
