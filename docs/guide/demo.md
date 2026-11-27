# Demo

A web app where you write messages, share documents, ask an AI assistant, and then check what the
assistant was shown, what was removed, and why.

## Run it on your machine

```bash
git clone https://github.com/humemai/audit-ready-memory
cd audit-ready-memory
uv run --extra demo streamlit run demo/app.py
```

The memory stays in `demo/data/`. Set `OPENROUTER_API_KEY` (for example in a `.env` file) to turn
the assistant on. The recalled text is then sent to OpenRouter.

## What to try

1. Load an example. It contains a message whose keep time has already passed.
2. On **Why**, pick an item to see which recalls read it, and the graph behind that.
3. On **Replay and delete**, remove an item with a reason, then move the replay slider back.
4. On the same tab, record the removal of expired items, and find that deletion on **Audit log**.

## Host it

The `Dockerfile` builds the hosted version. It needs a disk mounted for the memories and these
variables:

| Variable | Value |
|---|---|
| `ARM_DEMO_DATA` | Folder on the disk, `/data` in the image |
| `ARM_AUTH_REDIRECT_URI` | `https://<your address>/oauth2callback` |
| `ARM_AUTH_COOKIE_SECRET` | A long random string |
| `ARM_AUTH_GOOGLE_CLIENT_ID` | From a Google OAuth client of type "Web application" with that redirect address |
| `ARM_AUTH_GOOGLE_CLIENT_SECRET` | From the same client |
| `OPENROUTER_API_KEY` | Optional. Use a key of its own with a spending limit |

It refuses to start without the sign-in variables. Every account gets its own database. Run one
instance only, because a memory allows one writer.

| Limit | Default | Variable |
|---|---|---|
| AI replies per account per day | 30 | `ARM_DEMO_REPLIES_PER_ACCOUNT` |
| AI replies in total per day | 500 | `ARM_DEMO_REPLIES_TOTAL` |
| Length of a reply, in tokens | 600 | `ARM_DEMO_MAX_REPLY_TOKENS` |
| Events per memory | 1,000 | `ARM_DEMO_MAX_EVENTS` |
| Size of an uploaded file, in KB | 200 | `ARM_DEMO_MAX_UPLOAD_KB` |
| Characters kept from a document | 20,000 | `ARM_DEMO_MAX_DOCUMENT_CHARS` |
| Days without a visit before a memory is removed | 90 | `ARM_DEMO_KEEP_DAYS` |

## Privacy note of the hosted demo

**This is a demonstration, not a service. Use made-up information only.**

| Question | Answer |
|---|---|
| Who runs it | HumemAI. Contact: info@humem.ai |
| Signing in | With Google. The server keeps a hashed form of your account identifier to find your memory. The app does not write your name or email address to its own storage. Signing in sets a cookie in your browser |
| What is stored | What you type and upload, and the log of reads and deletions, in a database of your own |
| AI replies | Only when you ask the assistant: your message and the memory it recalls are sent to OpenRouter and the provider of the model |
| How long | Until you delete your account here, or 90 days after your last visit |
| Deleting everything | "Delete my account and data" removes your database from the server |
| Deleting one item | It is hidden from every read but stays in the log. That is how the library works, so that a removal can be shown to have happened |
| Also kept | A count of today's AI replies under the hashed identifier, until the day ends. The hosting provider keeps its own server logs, which can include your IP address |
