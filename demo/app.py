"""Streamlit demo: a memory you can inspect, replay, and delete from.

A small group writes messages, shares documents, and asks an AI assistant. Every write,
read, and deletion is an event in the memory log.

Run it on your own machine:

    uv run --extra demo streamlit run demo/app.py

Without an OPENROUTER_API_KEY everything works except the AI assistant.

The same app can be hosted with ``ARM_DEMO_HOSTED=1``: Google sign-in is then required, each
account gets its own database, and replies and uploads are limited. See ``demo/start.py``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

import hosting  # noqa: E402
from audit_ready_memory import (  # noqa: E402
    Assistant,
    Deletion,
    Document,
    Memory,
    Message,
    Recall,
)
from audit_ready_memory.assistant import OPENROUTER_BASE_URL  # noqa: E402

ASSISTANT_NAME = "assistant"
REPOSITORY = "https://github.com/humemai/audit-ready-memory"
KEEP_OPTIONS = {
    "Until I delete it": None,
    "1 minute": timedelta(minutes=1),
    "1 day": timedelta(days=1),
    "30 days": timedelta(days=30),
}
GRAPH_LIMIT = 60
log = logging.getLogger("audit-ready-memory-demo")


@st.cache_resource
def get_spaces(data_dir: str, idle_minutes: int, keep_days: int) -> hosting.Spaces:
    return hosting.Spaces(
        Path(data_dir), idle_close_seconds=idle_minutes * 60, keep_days=keep_days
    )


@st.cache_resource
def get_usage(data_dir: str, per_account: int, total: int) -> hosting.Usage:
    return hosting.Usage(
        Path(data_dir) / "usage.json", per_account=per_account, total=total
    )


def extract_text(name: str, data: bytes) -> tuple[str, str]:
    """Return (media_type, extracted_text) for an uploaded file."""
    suffix = name.lower().rsplit(".", 1)[-1]
    if suffix in ("txt", "md"):
        return "text/plain", data.decode("utf-8", errors="replace")
    if suffix == "csv":
        import pandas as pd

        return "text/csv", pd.read_csv(BytesIO(data)).to_string(index=False)
    if suffix == "xlsx":
        import pandas as pd

        sheets = pd.read_excel(BytesIO(data), sheet_name=None)
        text = "\n\n".join(
            f"## sheet: {sheet}\n{frame.to_string(index=False)}"
            for sheet, frame in sheets.items()
        )
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return media, text
    if suffix == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return "application/pdf", text
    raise ValueError(f"unsupported file type: .{suffix}")


def event_summary(event) -> str:
    if isinstance(event, Message):
        return f"{event.speaker}: {event.content}"
    if isinstance(event, Document):
        return f"uploaded {event.name} ({len(event.text)} characters)"
    if isinstance(event, Recall):
        return f"query {event.query!r} recalled {len(event.recalled)} item(s)"
    if isinstance(event, Deletion):
        return f"deleted {len(event.targets)} item(s): {event.reason}"
    return event.kind


def event_label(event) -> str:
    return f"#{event.seq} {event.kind}: {event_summary(event)[:60]}"


def now() -> datetime:
    return datetime.now(timezone.utc)


def keep_until(key: str) -> datetime | None:
    choice = st.selectbox("Keep it", list(KEEP_OPTIONS), key=key)
    span = KEEP_OPTIONS[choice]
    return None if span is None else now() + span


def chat_tab(memory: Memory, speaker: str, assistant, take_reply, full: bool):
    state = memory.replay()
    expired = {item.id for item in state.expired(now())}
    for message in state.visible_messages:
        is_ai = message.speaker == ASSISTANT_NAME
        with st.chat_message(
            "assistant" if is_ai else "user",
            avatar=":material/smart_toy:" if is_ai else ":material/person:",
        ):
            st.markdown(f"**{message.speaker}**: {message.content}")
            if message.id in expired:
                st.caption("Past its keep time: it is no longer recalled.")

    if "last_recall" in st.session_state:
        seq, lines = st.session_state["last_recall"]
        with st.expander(f"What the assistant was shown (Recall #{seq})"):
            for line in lines:
                st.write(f"- {line}")
    if "notice" in st.session_state:
        st.warning(st.session_state.pop("notice"))

    ask = st.toggle(
        "Ask the assistant",
        value=assistant is not None,
        disabled=assistant is None,
        help="Off: only write to the memory. On: the assistant replies, and what it "
        "was shown is logged as a Recall event.",
    )
    until = None if ask else keep_until("message-keep")
    prompt = st.chat_input("Say something", max_chars=2000, disabled=full)
    if not prompt:
        return
    if ask and assistant is not None and take_reply():
        try:
            reply = assistant.reply(prompt, speaker=speaker)
        except Exception:  # any failure of the AI service, whatever its type
            log.exception("assistant reply failed")
            st.session_state["notice"] = (
                "The assistant could not answer. Your message, and the record of what "
                "it was about to be shown, are in the log."
            )
        else:
            st.session_state["last_recall"] = (
                reply.recall.seq,
                [
                    f"`{item.kind}` #{item.seq}: {event_summary(item)[:120]}"
                    for item in reply.recalled
                ],
            )
    else:
        if ask:
            st.session_state["notice"] = (
                "No AI replies are left for today. Your message was saved."
            )
        memory.add_message(
            Message(speaker=speaker, content=prompt, source="chat", retain_until=until)
        )
    st.rerun()


def documents_tab(
    memory: Memory, speaker: str, settings: hosting.Settings, full: bool
):
    uploaded = st.file_uploader(
        "Upload a document (txt, md, csv, xlsx, pdf)",
        type=["txt", "md", "csv", "xlsx", "pdf"],
    )
    if uploaded is not None:
        data = uploaded.getvalue()
        sha256 = hashlib.sha256(data).hexdigest()
        already = any(
            doc.sha256 == sha256 for doc in memory.replay().visible_documents
        )
        if len(data) > settings.max_upload_kb * 1024:
            st.error(f"The file is larger than {settings.max_upload_kb} KB.")
        elif already:
            st.info("This exact file is already in memory.")
        else:
            until = keep_until("document-keep")
            if st.button(f"Save {uploaded.name} to memory", disabled=full):
                try:
                    media_type, text = extract_text(uploaded.name, data)
                except Exception:  # parsers fail in many ways on a bad file
                    log.exception("could not read an uploaded file")
                    st.error("This file could not be read.")
                else:
                    if not text.strip():
                        st.error("No text could be extracted from this file.")
                    else:
                        memory.add_document(
                            Document(
                                name=uploaded.name,
                                media_type=media_type,
                                text=text[: settings.max_document_chars],
                                sha256=sha256,
                                actor=speaker,
                                source="upload",
                                retain_until=until,
                            )
                        )
                        st.rerun()

    st.subheader("Documents")
    documents = memory.replay().visible_documents
    if not documents:
        st.caption("No documents yet.")
    for doc in documents:
        with st.expander(f"#{doc.seq} {doc.name} (from {doc.actor or 'unknown'})"):
            st.text(doc.text[:2000])


def audit_tab(memory: Memory):
    events = memory.events()
    if not events:
        st.caption("The log is empty.")
        return
    st.dataframe(
        [
            {
                "seq": event.seq,
                "kind": event.kind,
                "timestamp": event.timestamp.isoformat(timespec="seconds"),
                "summary": event_summary(event),
            }
            for event in events
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Append-only: every write, read, and deletion is a row here. "
        "Nothing is edited in place."
    )


def graph_source(memory: Memory, selected: int) -> str:
    """The memory graph in Graphviz form. Labels hold only numbers and kinds."""
    events = memory.events()
    edges = []
    for edge in ("NEXT", "RECALLED", "DELETED"):
        rows = memory.query(
            f"MATCH (a:MemoryEvent)-[:{edge}]->(b:MemoryEvent) "
            "RETURN a.seq AS source, b.seq AS target"
        )
        edges += [(row["source"], row["target"], edge) for row in rows]
    if len(events) > GRAPH_LIMIT:
        edges = [e for e in edges if selected in e[:2]]
    shown = {selected} | {seq for source, target, _ in edges for seq in (source, target)}
    lines = ["digraph memory {", "rankdir=LR;", 'node [shape=box, fontname="sans-serif"];']
    for event in events:
        if len(events) > GRAPH_LIMIT and event.seq not in shown:
            continue
        extra = ", penwidth=3" if event.seq == selected else ""
        lines.append(f'{event.seq} [label="#{event.seq} {event.kind}"{extra}];')
    lines += [f'{a} -> {b} [label="{edge}", fontsize=10];' for a, b, edge in edges]
    return "\n".join([*lines, "}"])


def why_tab(memory: Memory):
    items = [e for e in memory.events() if isinstance(e, (Message, Document))]
    if not items:
        st.caption("Write something first.")
        return
    item = st.selectbox("Pick an item", items, format_func=event_label)
    parameters = {"id": str(item.id)}
    recalls = memory.query(
        "MATCH (r:Recall)-[:RECALLED]->(m:MemoryEvent {id: $id}) "
        "RETURN r.seq AS seq, r.timestamp AS at ORDER BY seq",
        parameters,
    )
    removals = memory.query(
        "MATCH (d:Deletion)-[:DELETED]->(m:MemoryEvent {id: $id}) "
        "RETURN d.seq AS seq, d.timestamp AS at ORDER BY seq",
        parameters,
    )
    st.markdown("**Read by**")
    if not recalls:
        st.caption("No recall has read this item.")
    for row in recalls:
        recall = memory.events(after_seq=row["seq"] - 1, up_to_seq=row["seq"])[0]
        st.write(f"- #{row['seq']} at {row['at']}: query {recall.query!r}")
    st.markdown("**Removed by**")
    if not removals:
        st.caption("This item has not been deleted.")
    for row in removals:
        deletion = memory.events(after_seq=row["seq"] - 1, up_to_seq=row["seq"])[0]
        st.write(f"- #{row['seq']} at {row['at']}: {deletion.reason}")
    st.markdown("**The graph**")
    st.graphviz_chart(graph_source(memory, item.seq))
    with st.expander("The query behind “Read by”"):
        st.code(
            "MATCH (r:Recall)-[:RECALLED]->(m:MemoryEvent {id: $id})\n"
            "RETURN r.seq AS seq, r.timestamp AS at ORDER BY seq",
            language="cypher",
        )


def replay_delete_tab(memory: Memory, speaker: str, full: bool):
    st.subheader("Replay")
    total = len(memory)
    if total == 0:
        st.caption("Nothing to replay yet.")
    else:
        if total == 1:
            up_to = 0
            st.caption("One event in the log.")
        else:
            up_to = st.slider("Replay the log up to seq", 0, total - 1, total - 1)
        state = memory.replay(up_to_seq=up_to)
        st.write(
            f"At seq {up_to}: {len(state.visible_messages)} visible message(s), "
            f"{len(state.visible_documents)} visible document(s), "
            f"{len(state.deleted)} deleted item(s)."
        )
        for item in (*state.visible_messages, *state.visible_documents):
            st.write(f"- #{item.seq}: {event_summary(item)[:120]}")
        st.caption(
            "The same log always gives the same state. This covers the memory, "
            "not the wording of an AI reply."
        )

    st.subheader("Keep time")
    due = memory.replay().expired(now())
    st.write(f"{len(due)} item(s) are past their keep time.")
    if st.button("Record their removal", disabled=full or not due):
        memory.expire(requested_by=speaker)
        st.rerun()

    st.subheader("Delete")
    state = memory.replay()
    candidates = [*state.visible_messages, *state.visible_documents]
    if not candidates:
        st.caption("Nothing visible to delete.")
        return
    selected = st.multiselect("Items to delete", candidates, format_func=event_label)
    reason = st.text_input("Reason (required, goes in the audit log)", max_chars=200)
    if st.button("Delete", disabled=full or not (selected and reason.strip())):
        memory.delete(
            tuple(item.id for item in selected),
            reason=reason.strip(),
            requested_by=speaker,
        )
        st.rerun()


def privacy_note() -> str:
    return (HERE / "privacy.md").read_text(encoding="utf-8")


def funding_credit(container):
    container.image(str(HERE / "assets" / "sidn-fund-wordmark.png"), width=150)
    container.caption("Funded by [SIDN Fund](https://www.sidnfonds.nl/).")


def landing():
    """What a visitor sees before signing in."""
    st.title("Audit-Ready Memory")
    st.markdown(
        "A memory for AI assistants that you can inspect, replay, and delete from. "
        "Write messages, share a document, ask the assistant, and then check exactly "
        "what it was shown, what was removed, and why."
    )
    st.button("Sign in with Google", type="primary", on_click=st.login, args=("google",))
    st.caption("You get a private memory. Use made-up information only.")
    st.markdown("**Rather not sign in?** Run the same demo on your own machine:")
    st.code(
        f"git clone {REPOSITORY}\ncd audit-ready-memory\n"
        "uv run --extra demo streamlit run demo/app.py",
        language="bash",
    )
    with st.expander("Privacy"):
        st.markdown(privacy_note())
    funding_credit(st)


def assistant_for(memory: Memory, settings: hosting.Settings, model: str):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    from openai import OpenAI

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key, timeout=60)
    if settings.hosted:
        client = hosting.capped_client(client, max_tokens=settings.max_reply_tokens)
    return Assistant(memory, client=client, model=model, name=ASSISTANT_NAME)


def workspace(memory: Memory, settings: hosting.Settings, account: str):
    sidebar = st.sidebar
    speaker = sidebar.text_input("Speak as", value="coordinator", max_chars=40)
    speaker = speaker.strip() or "coordinator"
    model = settings.model
    if not settings.hosted:
        model = sidebar.text_input("OpenRouter model", value=model)

    assistant = assistant_for(memory, settings, model)
    usage = None
    if assistant is None:
        sidebar.warning(
            "The assistant is off: no AI key is configured. Everything else works."
        )
    elif settings.hosted:
        usage = get_usage(
            str(settings.data_dir),
            settings.replies_per_account,
            settings.replies_total,
        )
        left = usage.remaining(account)
        sidebar.caption(f"{left} AI replies left today. Model: {model}.")
        if not left:
            assistant = None

    def take_reply() -> bool:
        return usage is None or usage.take(account)

    full = settings.hosted and len(memory) >= settings.max_events
    sidebar.caption(
        f"{len(memory)} event(s) in your log"
        + (f" (limit {settings.max_events})." if settings.hosted else ".")
    )
    if full:
        st.warning("This demo memory is full. Delete your data to start again.")

    if len(memory) == 0:
        st.info("The memory is empty. Load an example, or start writing.")
        for title, scenario in hosting.scenarios().items():
            if st.button(f"Load example: {title}", help=scenario["description"]):
                hosting.load_scenario(memory, scenario)
                st.rerun()

    chat, documents, audit, why, replay = st.tabs(
        ["Chat", "Documents", "Audit log", "Why", "Replay and delete"]
    )
    with chat:
        chat_tab(memory, speaker, assistant, take_reply, full)
    with documents:
        documents_tab(memory, speaker, settings, full)
    with audit:
        audit_tab(memory)
    with why:
        why_tab(memory)
    with replay:
        replay_delete_tab(memory, speaker, full)

    with sidebar.expander("Privacy"):
        st.markdown(privacy_note())
    label = "Delete my account and data" if settings.hosted else "Delete this memory"
    sure = sidebar.checkbox("I want to delete everything. This cannot be undone.")
    if sidebar.button(label, disabled=not sure):
        st.session_state["delete_requested"] = True
        st.rerun()
    if settings.hosted:
        sidebar.button("Sign out", on_click=st.logout)
    sidebar.markdown(f"[Source code and documentation]({REPOSITORY})")
    funding_credit(sidebar)


def main():
    st.set_page_config(
        page_title="Audit-Ready Memory",
        page_icon=str(HERE / "assets" / "icon.png"),
    )
    if os.environ.get("ARM_DEMO_HOSTED") != "1":
        load_dotenv()
    settings = hosting.Settings.from_env()
    account = hosting.LOCAL_ACCOUNT
    if settings.hosted:
        if not st.user.get("is_logged_in", False):
            landing()
            return
        account = hosting.account_key(
            str(st.user.get("iss", "")), str(st.user.get("sub", ""))
        )
    spaces = get_spaces(
        str(settings.data_dir), settings.idle_close_minutes, settings.keep_days
    )
    # outside the block below: deleting needs the memory to be released
    if st.session_state.pop("delete_requested", False):
        spaces.delete(account)
        st.session_state.clear()
        if settings.hosted:
            st.logout()
            return
    st.title("Audit-Ready Memory")
    st.caption("A memory you can inspect, replay, and delete from.")
    with spaces.use(account) as memory:
        workspace(memory, settings, account)


main()
