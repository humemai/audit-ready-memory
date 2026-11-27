"""The Streamlit app runs, locally and signed out. No network and no AI calls."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parent.parent / "demo" / "app.py")


@pytest.fixture(autouse=True)
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ARM_DEMO_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("ARM_DEMO_HOSTED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")


def _app() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    assert not app.exception, app.exception
    return app


def _button(app, start: str):
    return next(b for b in app.button if b.label.startswith(start))


def test_local_app_loads_an_example_and_shows_it():
    app = _app()
    _button(app, "Load example: Neighbourhood").click().run()
    assert not app.exception, app.exception
    shown = " ".join(markdown.value for markdown in app.markdown)
    assert "water pump on Elm Street" in shown
    assert len(app.tabs) == 5


def test_writing_a_message_adds_it():
    app = _app()
    app.chat_input[0].set_value("the bench is repaired").run()
    assert not app.exception, app.exception
    assert any("the bench is repaired" in m.value for m in app.markdown)


def test_deleting_everything_empties_the_memory():
    app = _app()
    app.chat_input[0].set_value("remove me").run()
    app.sidebar.checkbox[0].check().run()
    _button(app, "Delete this memory").click().run()
    assert not app.exception, app.exception
    assert not any("remove me" in m.value for m in app.markdown)
    assert any("empty" in info.value for info in app.info)


def test_hosted_visitor_must_sign_in(tmp_path, monkeypatch):
    monkeypatch.setenv("ARM_DEMO_HOSTED", "1")
    app = _app()
    assert [b.label for b in app.button] == ["Sign in with Google"]
    assert not app.tabs and not app.chat_input
    assert not (tmp_path / "data").exists()
