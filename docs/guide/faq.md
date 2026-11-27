# Questions

### Does my data leave my machine?

Not by the library. The optional assistant sends your question and the recalled items to the model
service you configure, which by default is a cloud service. The demo does the same when you ask the
assistant.

### Is deleted data really gone?

No. It is hidden from every read and stays in the log, so that the removal can be shown. To erase
everything, delete the memory folder. See [retention and deletion](retention-and-deletion.md).

### What happens when a keep time passes?

Recalls and the assistant stop using the entry at once. The removal is written to the log when you
call `expire()`.

### Can I see what the AI was shown last week?

Yes. Every recall is an event that names the items. `memory.events(kind="recall")` lists them, and
replaying up to that event shows the memory as it was then.

### Can someone change the log without me noticing?

Someone with write access to the files can. The log is not signed or chained. Protect the folder.

### Do I need a database server?

No. The database runs inside your program and keeps its files in one folder.

### Which AI models work?

Any service with an OpenAI-compatible interface, including one on your own machine. Without a model,
everything except the assistant works.

### Can I use it for real personal data?

Read [privacy and data flow](privacy-and-data-flow.md) first. The main question is whether you may
have to erase single entries, which the library cannot do.

### Can I reuse or change it?

Yes, under the MIT license. See [reuse and citation](reuse.md).
