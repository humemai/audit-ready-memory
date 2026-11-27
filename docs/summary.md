# In one page

## The problem

AI assistants increasingly remember things. Often nobody can see what they remember, what they used
for an answer, or whether something was really removed after a request. For public organisations,
community groups, and researchers, that makes it hard to explain a decision, to correct a mistake,
or to answer a privacy request.

## What this project is

A small, free, open-source memory for AI assistants that keeps a diary. Everything written, every
time something is looked up, and every removal is noted in order. It runs on your own computer.

## What you can do with it

- **See** everything the memory holds, and its history.
- **Check** what an assistant was given for an answer.
- **Go back** to how the memory looked at an earlier moment.
- **Remove** an entry with a reason, so that it is no longer used and the removal is on record.
- **Limit** how long an entry may be used.

## What it does not do

It does not erase single entries from disk, it cannot prove that nobody tampered with its files,
and its search only matches words. It is a building block and a demonstration, not a finished
product.

## Why it matters

Being able to show what a system knew and used is a basis for trust and accountability. Keeping the
memory local lets an organisation decide where its data lives.

## Try it

Run the [demo](guide/demo.md), or read the two [walkthroughs](guide/walkthroughs.md).

Made by HumemAI, funded by [SIDN Fund](https://www.sidnfonds.nl/). Licensed under MIT.

## Words used

| Word | Meaning |
|---|---|
| Event | One line in the diary: something written, looked up, or removed |
| Log | All events in order |
| Recall | Looking something up in the memory, which is itself noted |
| Replay | Rebuilding how the memory looked from the log |
| Deletion (tombstone) | A note that an entry is removed. The entry is hidden, not erased |
| Keep time (retention) | How long an entry may be used |
| Local-first | The data stays on a machine you control |
