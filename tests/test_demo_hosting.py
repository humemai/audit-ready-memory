"""Tests for what the demo adds: separate memories, deletion, limits, and examples."""

import os
import threading
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from audit_ready_memory import Message
from demo import hosting, start


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def spaces(tmp_path, clock):
    opened = hosting.Spaces(
        tmp_path, idle_close_seconds=1800, keep_days=90, clock=clock
    )
    yield opened
    opened.close()


def _say(memory, text):
    memory.add_message(Message(speaker="a", content=text))


def _texts(spaces, key):
    with spaces.use(key) as memory:
        return [m.content for m in memory.replay().visible_messages]


class TestAccountKey:
    def test_stable_and_hides_the_identifier(self):
        key = hosting.account_key("https://accounts.google.com", "1234567890")
        assert key == hosting.account_key("https://accounts.google.com", "1234567890")
        assert "1234567890" not in key and key.isalnum() and len(key) == 32

    def test_differs_by_subject_and_issuer(self):
        keys = {
            hosting.account_key("a", "1"),
            hosting.account_key("a", "2"),
            hosting.account_key("b", "1"),
        }
        assert len(keys) == 3

    def test_missing_subject_is_refused(self):
        with pytest.raises(ValueError):
            hosting.account_key("a", "")


class TestSpaces:
    def test_accounts_do_not_see_each_other(self, spaces):
        with spaces.use("alice") as memory:
            _say(memory, "from alice")
        with spaces.use("bob") as memory:
            _say(memory, "from bob")
        assert _texts(spaces, "alice") == ["from alice"]
        assert _texts(spaces, "bob") == ["from bob"]

    def test_idle_memory_is_closed_and_comes_back(self, spaces, clock):
        with spaces.use("alice") as memory:
            _say(memory, "kept")
        assert spaces.close_idle() == []
        clock.now += 1801
        assert spaces.close_idle() == ["alice"]
        assert not spaces.is_open("alice")
        assert _texts(spaces, "alice") == ["kept"]

    def test_a_memory_in_use_is_not_closed(self, spaces, clock):
        with spaces.use("alice") as memory:
            clock.now += 10_000
            assert spaces.close_idle() == []
            _say(memory, "still open")

    def test_delete_removes_the_folder(self, spaces, tmp_path):
        with spaces.use("alice") as memory:
            _say(memory, "gone")
        folder = tmp_path / "spaces" / "alice"
        assert folder.exists()
        spaces.delete("alice")
        assert not folder.exists()
        assert _texts(spaces, "alice") == []

    def test_delete_of_an_unknown_account_is_harmless(self, spaces):
        spaces.delete("nobody")

    def test_old_memories_are_purged_and_recent_ones_kept(self, spaces, clock, tmp_path):
        with spaces.use("old") as memory:
            _say(memory, "old")
        clock.now += 80 * 86_400
        with spaces.use("recent") as memory:
            _say(memory, "recent")
        clock.now += 11 * 86_400
        assert spaces.purge_stale() == ["old"]
        assert not (tmp_path / "spaces" / "old").exists()
        assert _texts(spaces, "recent") == ["recent"]

    def test_a_key_cannot_leave_the_folder(self, spaces):
        with pytest.raises(ValueError):
            with spaces.use("../escape"):
                pass

    def test_concurrent_writers_of_one_account_take_turns(self, spaces):
        failures = []

        def write():
            try:
                for n in range(10):
                    with spaces.use("alice") as memory:
                        _say(memory, str(n))
            except Exception as error:  # noqa: BLE001 - reported by the assert
                failures.append(error)

        threads = [threading.Thread(target=write) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert failures == []
        with spaces.use("alice") as memory:
            assert [event.seq for event in memory.events()] == list(range(40))


class TestUsage:
    def _usage(self, tmp_path, day, **limits):
        return hosting.Usage(tmp_path / "usage.json", today=lambda: day[0], **limits)

    def test_per_account_limit(self, tmp_path):
        day = [date(2026, 12, 1)]
        usage = self._usage(tmp_path, day, per_account=2, total=100)
        assert [usage.take("a"), usage.take("a"), usage.take("a")] == [True, True, False]
        assert usage.remaining("a") == 0
        assert usage.remaining("b") == 2

    def test_total_limit(self, tmp_path):
        day = [date(2026, 12, 1)]
        usage = self._usage(tmp_path, day, per_account=5, total=2)
        assert [usage.take("a"), usage.take("b"), usage.take("c")] == [True, True, False]
        assert usage.remaining("d") == 0

    def test_resets_the_next_day_and_survives_a_restart(self, tmp_path):
        day = [date(2026, 12, 1)]
        self._usage(tmp_path, day, per_account=1, total=9).take("a")
        again = self._usage(tmp_path, day, per_account=1, total=9)
        assert again.take("a") is False
        day[0] = date(2026, 12, 2)
        assert again.take("a") is True


class TestCappedClient:
    def test_caps_length_and_switches_reasoning_off(self):
        seen = {}
        inner = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kw: seen.update(kw))
            )
        )
        hosting.capped_client(inner, max_tokens=50).chat.completions.create(
            model="m", messages=[]
        )
        assert seen["max_tokens"] == 50
        assert seen["extra_body"] == {"reasoning": {"enabled": False}}


class TestScenarios:
    def test_public_interest_example_comes_first(self):
        assert next(iter(hosting.scenarios())) == "Neighbourhood water pump"

    @pytest.mark.parametrize("title", list(hosting.scenarios()))
    def test_loads_and_shows_an_expired_item(self, spaces, title):
        scenario = hosting.scenarios()[title]
        with spaces.use("a") as memory:
            count = hosting.load_scenario(memory, scenario)
            assert len(memory) == count
            expired = memory.replay().expired(memory.events()[-1].timestamp)
            assert len(expired) == 1
            _, hits = memory.recall(expired[0].content)
            assert expired[0] not in hits


class TestScenarioRecalls:
    @pytest.mark.parametrize("title", list(hosting.scenarios()))
    def test_example_has_a_read_to_look_at(self, spaces, title):
        with spaces.use("a") as memory:
            hosting.load_scenario(memory, hosting.scenarios()[title])
            recall = memory.events(kind="recall")[0]
            assert recall.recalled


class TestPrivacyPage:
    def test_docs_show_the_note_the_app_shows(self):
        root = Path(hosting.__file__).parent.parent
        note = (root / "demo" / "privacy.md").read_text(encoding="utf-8")
        assert note.strip() in (root / "docs" / "guide" / "demo.md").read_text(
            encoding="utf-8"
        )


class TestSettings:
    def test_local_defaults(self):
        settings = hosting.Settings.from_env({})
        assert not settings.hosted and settings.data_dir.name == "data"

    def test_hosted_needs_a_data_folder(self):
        with pytest.raises(RuntimeError):
            hosting.Settings.from_env({"ARM_DEMO_HOSTED": "1"})

    def test_limits_come_from_the_environment(self):
        settings = hosting.Settings.from_env(
            {"ARM_DEMO_HOSTED": "1", "ARM_DEMO_DATA": "/d", "ARM_DEMO_REPLIES_TOTAL": "7"}
        )
        assert settings.hosted and settings.replies_total == 7


class TestStart:
    ENV = {name: f'value of "{name}"' for name in start.REQUIRED}

    def test_names_every_missing_variable(self):
        assert start.missing({}) == list(start.REQUIRED)
        assert start.missing(self.ENV) == []

    def test_secrets_file_is_valid_toml(self):
        import tomllib

        parsed = tomllib.loads(start.secrets_toml(self.ENV))
        google = parsed["auth"]["google"]
        assert google["client_id"] == self.ENV["ARM_AUTH_GOOGLE_CLIENT_ID"]
        assert parsed["auth"]["cookie_secret"] == self.ENV["ARM_AUTH_COOKIE_SECRET"]

    def test_refuses_to_start_without_sign_in(self, monkeypatch):
        for name in start.REQUIRED:
            monkeypatch.delenv(name, raising=False)
        with pytest.raises(SystemExit):
            start.main()
        assert os.environ.get("ARM_DEMO_HOSTED") != "1"
