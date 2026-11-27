# Walkthroughs

Two complete examples, each described in words first so that you can follow them without running
anything. To run them, clone the repository and use `uv run python examples/<name>.py`.

## A removal request

A resident reports a broken pump and includes a phone number. Later they ask for it to be removed.

1. Two messages are written. They become events 0 and 1.
2. A search for "pump" returns both, and the search itself is recorded as event 2.
3. The resident's message is deleted, with a reason and who asked. That is event 3.
4. The same search now returns only the other message.
5. The log answers three questions afterwards: which event removed the message and why, which
   earlier searches had read it, and whether the original is still stored. It is: deleting hides
   content from every read but does not erase it.

```python
--8<-- "examples/removal_request.py"
```

It prints:

```text
recalled before the removal: [0, 1]
recalled after the removal: [1]
removed by event 3: the resident asked to remove the phone number
read by events: [2]
original still in the log: True
```

!!! warning "If the data must be erased"
    The last line is the limit of this library. If you must remove the bytes themselves, read
    [retention and deletion](retention-and-deletion.md#when-that-is-not-enough) before storing the
    data.

## Looking back, with an entry that expires

A coordinator notes a repair date and a gate code. The code has a keep time that has already passed.

1. Both are written as events 0 and 1.
2. A search for "repair" returns only the date. The expired code is left out, and the search is
   recorded as event 2.
3. Recording the expiry writes event 3, a deletion that names the code.
4. A correction is written as event 4.
5. Replaying up to event 2 shows what was in memory at the time of the search. Replaying
   everything shows what is in memory now.

```python
--8<-- "examples/look_back.py"
```

It prints:

```text
shown then: ['the repair is planned for Monday']
expiry recorded as event 3: 1 item
in memory at the first recall: 2 items
in memory now: ['the repair is planned for Monday', 'the repair moves to Tuesday']
recall counts: [1]
```

At the first search the code was still in memory, but it was already past its keep time, so it was
not shown.
