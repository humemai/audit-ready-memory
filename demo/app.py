"""Streamlit demo: a small group chatting with each other and an AI,
sharing documents, on top of an audit-ready memory.

Run with:

    uv run --extra demo streamlit run demo/app.py

Without an OPENROUTER_API_KEY the app still runs (chat between humans,
uploads, audit log, replay, deletion); only the AI assistant is disabled.
"""

import hashlib
from io import BytesIO
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from audit_ready_memory import (
    Assistant,
    Deletion,
    Document,
    Memory,
    Message,
    MissingAPIKeyError,
    Recall,
)

load_dotenv()

DB_PATH = str(Path(__file__).parent / "demo-db")
ASSISTANT_NAME = "humemai"


@st.cache_resource
def get_memory() -> Memory:
    return Memory(DB_PATH)


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
        return f"uploaded {event.name} ({len(event.text)} chars)"
    if isinstance(event, Recall):
        return f"query {event.query!r} recalled {len(event.recalled)} item(s)"
    if isinstance(event, Deletion):
        return f"deleted {len(event.targets)} item(s): {event.reason}"
    return event.kind


def event_label(event) -> str:
    return f"#{event.seq} {event.kind}: {event_summary(event)[:60]}"


def chat_tab(memory: Memory, speaker: str, assistant: Assistant | None):
    state = memory.replay()
    for message in state.visible_messages:
        role = "assistant" if message.speaker == ASSISTANT_NAME else "user"
        with st.chat_message(role):
            st.markdown(f"**{message.speaker}**: {message.content}")

    ask_ai = st.toggle(
        "Ask the assistant",
        value=assistant is not None,
        disabled=assistant is None,
        help="Off: message the group only. On: the AI replies, and the "
        "memory it was shown is logged as a Recall event.",
    )
    prompt = st.chat_input("Say something to the group")
    if prompt:
        if ask_ai and assistant is not None:
            reply = assistant.reply(prompt, speaker=speaker)
            with st.expander(
                f"What entered the AI's context (Recall #{reply.recall.seq})"
            ):
                for item in reply.recalled:
                    st.write(f"- `{item.kind}` #{item.seq}: {event_summary(item)[:120]}")
        else:
            memory.add_message(Message(speaker=speaker, content=prompt, source="chat"))
        st.rerun()


def documents_tab(memory: Memory, speaker: str):
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
        if already:
            st.info("This exact file is already in memory.")
        elif st.button(f"Save {uploaded.name} to memory"):
            try:
                media_type, text = extract_text(uploaded.name, data)
            except ValueError as error:
                st.error(str(error))
            else:
                if not text.strip():
                    st.error("No text could be extracted from this file.")
                else:
                    memory.add_document(
                        Document(
                            name=uploaded.name,
                            media_type=media_type,
                            text=text,
                            sha256=sha256,
                            actor=speaker,
                            source="upload",
                        )
                    )
                    st.rerun()

    st.subheader("Shared documents")
    documents = memory.replay().visible_documents
    if not documents:
        st.caption("No documents yet.")
    for doc in documents:
        with st.expander(f"#{doc.seq} {doc.name} (uploaded by {doc.actor or 'unknown'})"):
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
        "Nothing is ever edited in place."
    )


def replay_delete_tab(memory: Memory, speaker: str):
    st.subheader("Replay")
    total = len(memory)
    if total == 0:
        st.caption("Nothing to replay yet.")
    else:
        if total == 1:
            up_to = 0
            st.caption("One event in the log; replaying up to seq 0.")
        else:
            up_to = st.slider("Replay the log up to seq", 0, total - 1, total - 1)
        state = memory.replay(up_to_seq=up_to)
        st.write(
            f"At seq {up_to}: {len(state.visible_messages)} visible message(s), "
            f"{len(state.visible_documents)} visible document(s), "
            f"{len(state.deleted)} deleted item(s)."
        )
        st.caption(
            "Same log, same state — deterministic replay applies to memory, "
            "not to LLM wording."
        )

    st.subheader("Delete")
    state = memory.replay()
    candidates = [*state.visible_messages, *state.visible_documents]
    if not candidates:
        st.caption("Nothing visible to delete.")
        return
    selected = st.multiselect(
        "Items to delete", candidates, format_func=event_label
    )
    reason = st.text_input("Reason (required, goes in the audit log)")
    if st.button("Delete", disabled=not (selected and reason.strip())):
        memory.delete(
            tuple(item.id for item in selected),
            reason=reason.strip(),
            requested_by=speaker,
        )
        st.rerun()


def main():
    st.set_page_config(page_title="Audit-Ready Memory", page_icon=None)
    st.title("Audit-Ready Memory — group demo")

    memory = get_memory()
    speaker = st.sidebar.text_input("Your name", value="anna")
    model = st.sidebar.text_input("OpenRouter model", value="openai/gpt-4o-mini")
    try:
        assistant = Assistant(memory, model=model, name=ASSISTANT_NAME)
    except MissingAPIKeyError:
        assistant = None
        st.sidebar.warning(
            "No OPENROUTER_API_KEY set — the AI is disabled. Chat between "
            "humans, uploads, audit log, replay, and deletion still work."
        )
    st.sidebar.caption(
        f"Memory: {len(memory)} event(s) in an append-only local log at "
        f"`{DB_PATH}`. The API key is never stored there."
    )

    chat, documents, audit, replay_delete = st.tabs(
        ["Chat", "Documents", "Audit log", "Replay & delete"]
    )
    with chat:
        chat_tab(memory, speaker, assistant)
    with documents:
        documents_tab(memory, speaker)
    with audit:
        audit_tab(memory)
    with replay_delete:
        replay_delete_tab(memory, speaker)


main()
