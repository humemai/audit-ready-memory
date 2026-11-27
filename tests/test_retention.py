"""Tests for retention: expired content is not recalled, and expiry is logged."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from audit_ready_memory import (
    Assistant,
    Document,
    Memory,
    Message,
    Recall,
    replay,
    search,
)

NOON = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
SECOND = timedelta(seconds=1)


@pytest.fixture
def memory(tmp_path):
    with Memory(tmp_path / "db") as m:
        yield m


def _past() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=1)


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=1)


def _message(content: str, seq: int, retain_until=None) -> Message:
    return Message(
        speaker="user", content=content, retain_until=retain_until
    ).model_copy(update={"seq": seq})


class TestExpiredState:
    def test_boundary_is_inclusive(self):
        state = replay([_message("door code", 0, NOON)])
        assert state.expired(NOON - SECOND) == ()
        assert state.expired(NOON) == state.messages
        assert state.expired(NOON + SECOND) == state.messages

    def test_no_retain_until_never_expires(self):
        state = replay([_message("keep", 0)])
        assert state.expired(NOON + timedelta(days=36500)) == ()

    def test_log_order_across_kinds(self):
        document = Document(
            name="a.txt", text="a", retain_until=NOON
        ).model_copy(update={"seq": 0})
        message = _message("b", 1, NOON)
        assert replay([document, message]).expired(NOON) == (document, message)

    def test_naive_time_rejected(self):
        with pytest.raises(ValueError):
            replay([]).expired(datetime(2026, 6, 1))

    def test_expiry_alone_does_not_change_visibility(self):
        state = replay([_message("old", 0, NOON)])
        assert state.visible_messages == state.messages

    def test_search_filters_only_with_a_time(self):
        state = replay([_message("door code", 0, NOON)])
        assert search(state, "door") == list(state.messages)
        assert search(state, "door", as_of=NOON) == []


class TestRecall:
    def test_expired_content_is_not_recalled(self, memory):
        memory.add_message(
            Message(speaker="anna", content="door code 4471", retain_until=_past())
        )
        kept = memory.add_message(
            Message(speaker="anna", content="door repaired", retain_until=_future())
        )
        recall, hits = memory.recall("door")
        assert hits == [kept]
        assert recall.recalled == (kept.id,)

    def test_manual_record_of_expired_item_is_kept(self, memory):
        old = memory.add_message(
            Message(speaker="anna", content="old", retain_until=_past())
        )
        recall = memory.record_recall(Recall(query="q", recalled=(old.id,)))
        assert recall.recalled == (old.id,)

    def test_assistant_context_leaves_expired_content_out(self, memory):
        calls = []

        def create(*, model, messages):
            calls.append(messages)
            reply = SimpleNamespace(content="ok")
            return SimpleNamespace(choices=[SimpleNamespace(message=reply)])

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        kept = memory.add_message(Message(speaker="anna", content="pump is fine"))
        memory.add_message(
            Message(speaker="anna", content="door code 4471", retain_until=_past())
        )
        # one recent turn besides the question: the slot must go to the kept one
        reply = Assistant(memory, client=client, recent_turns=2).reply(
            "what is the door code", speaker="bo"
        )
        assert "4471" not in calls[0][1]["content"]
        assert kept.id in reply.recall.recalled


class TestExpire:
    def test_appends_one_deletion_for_everything_due(self, memory):
        first = memory.add_message(
            Message(speaker="anna", content="a", retain_until=_past())
        )
        document = memory.add_document(
            Document(name="b.txt", text="b", retain_until=_past())
        )
        kept = memory.add_message(
            Message(speaker="anna", content="c", retain_until=_future())
        )
        deletion = memory.expire(requested_by="nightly job")
        assert deletion.targets == (first.id, document.id)
        assert deletion.requested_by == "nightly job"
        assert deletion.reason.startswith("retention period elapsed (as of ")
        assert memory.replay().visible_messages == (kept,)
        assert memory.replay().visible_documents == ()
        assert memory.events(kind="deletion") == [deletion]

    def test_second_call_writes_nothing(self, memory):
        memory.add_message(Message(speaker="anna", content="a", retain_until=_past()))
        memory.expire()
        size = len(memory)
        assert memory.expire() is None
        assert len(memory) == size

    def test_as_of_selects_what_was_due_then(self, memory):
        early = memory.add_message(
            Message(speaker="anna", content="a", retain_until=NOON)
        )
        memory.add_message(
            Message(speaker="anna", content="b", retain_until=NOON + SECOND)
        )
        assert memory.expire(as_of=NOON).targets == (early.id,)

    def test_future_time_rejected(self, memory):
        memory.add_message(Message(speaker="anna", content="a", retain_until=_future()))
        with pytest.raises(ValueError):
            memory.expire(as_of=_future() + timedelta(days=1))
        assert len(memory) == 1

    def test_naive_time_rejected(self, memory):
        with pytest.raises(ValueError):
            memory.expire(as_of=datetime(2026, 6, 1))
        assert len(memory) == 0
