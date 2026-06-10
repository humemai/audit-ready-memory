"""Tests for the assistant loop, using a stub LLM client (no network)."""

from types import SimpleNamespace

import pytest

from audit_ready_memory import (
    Assistant,
    Document,
    Memory,
    Message,
    MissingAPIKeyError,
)


class StubClient:
    """OpenAI-compatible stub that records calls and returns a canned reply."""

    def __init__(self, reply_text="canned reply"):
        self.calls = []
        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)
        self._reply_text = reply_text

    def _create(self, *, model, messages):
        self.calls.append({"model": model, "messages": messages})
        message = SimpleNamespace(content=self._reply_text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def memory(tmp_path):
    with Memory(tmp_path / "db") as m:
        yield m


def make_assistant(memory, **kwargs) -> tuple[Assistant, StubClient]:
    client = StubClient(**kwargs)
    return Assistant(memory, client=client, name="humemai"), client


class TestMissingKey:
    def test_raises_without_key_or_client(self, memory, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError):
            Assistant(memory)


class TestReply:
    def test_logs_question_recall_and_answer(self, memory):
        assistant, _ = make_assistant(memory)
        reply = assistant.reply("what is the budget?", speaker="anna")
        kinds = [event.kind for event in memory.events()]
        assert kinds == ["message", "recall", "message"]
        assert reply.message.speaker == "humemai"
        assert reply.message.content == "canned reply"
        assert memory.get(reply.recall.id) == reply.recall

    def test_recall_matches_context_sent_to_llm(self, memory):
        memory.add_message(Message(speaker="bob", content="the budget is 10k"))
        memory.add_document(Document(name="budget-plan.txt", text="spend wisely"))
        assistant, client = make_assistant(memory)
        reply = assistant.reply("what is the budget?", speaker="anna")
        prompt_text = client.calls[0]["messages"][1]["content"]
        for item in reply.recalled:
            assert item.id in reply.recall.recalled
        assert "the budget is 10k" in prompt_text
        assert "spend wisely" in prompt_text
        assert set(reply.recall.recalled) == {item.id for item in reply.recalled}

    def test_deleted_content_never_enters_context(self, memory):
        secret = memory.add_message(Message(speaker="bob", content="budget secret"))
        memory.delete((secret.id,), reason="user request")
        assistant, client = make_assistant(memory)
        reply = assistant.reply("tell me about the budget", speaker="anna")
        prompt_text = client.calls[0]["messages"][1]["content"]
        assert "budget secret" not in prompt_text
        assert secret.id not in reply.recall.recalled

    def test_recall_recorded_before_llm_reply(self, memory):
        assistant, _ = make_assistant(memory)
        reply = assistant.reply("hello", speaker="anna")
        recall_seq = reply.recall.seq
        assert recall_seq < reply.message.seq

    def test_system_prompt_is_first_message(self, memory):
        assistant, client = make_assistant(memory)
        assistant.reply("hello", speaker="anna")
        assert client.calls[0]["messages"][0]["role"] == "system"
        assert client.calls[0]["messages"][0]["content"] == assistant.system_prompt

    def test_session_id_propagates(self, memory):
        assistant, _ = make_assistant(memory)
        assistant.reply("hello", speaker="anna", session_id="s1")
        assert all(event.session_id == "s1" for event in memory.events())
