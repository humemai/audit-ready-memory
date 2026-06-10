"""Tests for naive keyword retrieval and the recall workflow."""

from audit_ready_memory import Document, Memory, Message, replay, search


def _message(content: str, seq: int, speaker: str = "user") -> Message:
    return Message(speaker=speaker, content=content).model_copy(update={"seq": seq})


def _document(name: str, text: str, seq: int) -> Document:
    return Document(name=name, text=text).model_copy(update={"seq": seq})


class TestSearch:
    def test_matches_by_keyword(self):
        a = _message("the budget meeting is on friday", 0)
        b = _message("cats are great", 1)
        state = replay([a, b])
        assert search(state, "budget") == [a]

    def test_case_insensitive(self):
        a = _message("The Budget Meeting", 0)
        state = replay([a])
        assert search(state, "BUDGET") == [a]

    def test_matches_documents_by_name_and_text(self):
        d = _document("budget.txt", "quarterly numbers", 0)
        state = replay([d])
        assert search(state, "budget") == [d]
        assert search(state, "quarterly") == [d]

    def test_matches_message_speaker(self):
        a = _message("see you tomorrow", 0, speaker="anna")
        state = replay([a])
        assert search(state, "anna") == [a]

    def test_ranks_by_overlap_then_log_order(self):
        one = _message("budget", 0)
        two = _message("budget meeting", 1)
        also_two = _message("budget meeting notes", 2)
        state = replay([one, two, also_two])
        assert search(state, "budget meeting") == [two, also_two, one]

    def test_respects_limit(self):
        events = [_message(f"budget {i}", i) for i in range(10)]
        state = replay(events)
        assert len(search(state, "budget", limit=3)) == 3

    def test_no_match_returns_empty(self):
        state = replay([_message("hello", 0)])
        assert search(state, "zebra") == []

    def test_empty_query_returns_empty(self):
        state = replay([_message("hello", 0)])
        assert search(state, "   ") == []


class TestSearchExcludesDeleted:
    def test_deleted_message_never_recalled(self, tmp_path):
        with Memory(tmp_path / "db") as memory:
            kept = memory.add_message(Message(speaker="user", content="budget plan"))
            gone = memory.add_message(Message(speaker="user", content="budget secret"))
            memory.delete((gone.id,), reason="user request")
            assert search(memory.replay(), "budget") == [kept]


class TestMemoryRecall:
    def test_recall_logs_exactly_what_it_returns(self, tmp_path):
        with Memory(tmp_path / "db") as memory:
            m = memory.add_message(Message(speaker="anna", content="budget meeting"))
            memory.add_message(Message(speaker="bob", content="unrelated chat"))
            recall, items = memory.recall("budget")
            assert items == [m]
            assert recall.recalled == (m.id,)
            assert memory.get(recall.id) == recall

    def test_recall_with_no_match_logs_empty(self, tmp_path):
        with Memory(tmp_path / "db") as memory:
            memory.add_message(Message(speaker="anna", content="hello"))
            recall, items = memory.recall("zebra")
            assert items == []
            assert recall.recalled == ()

    def test_recall_updates_stats(self, tmp_path):
        with Memory(tmp_path / "db") as memory:
            m = memory.add_message(Message(speaker="anna", content="budget"))
            memory.recall("budget")
            memory.recall("budget")
            assert memory.replay().recall_stats[m.id].num_recalled == 2
