"""Find out later what was known and what was shown, with an entry that expires.

Run from a clone: uv run python examples/look_back.py
"""

import tempfile
from datetime import datetime, timedelta, timezone

from audit_ready_memory import Memory, Message

with tempfile.TemporaryDirectory() as folder:
    with Memory(f"{folder}/memory") as memory:
        memory.add_message(
            Message(speaker="coordinator", content="the repair is planned for Monday")
        )
        a_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
        memory.add_message(
            Message(
                speaker="coordinator",
                content="the gate code for the repair is 4471",
                retain_until=a_minute_ago,
            )
        )

        first, hits = memory.recall("repair")
        print("shown then:", [hit.content for hit in hits])

        sweep = memory.expire(requested_by="coordinator")
        print(f"expiry recorded as event {sweep.seq}: {len(sweep.targets)} item")

        memory.add_message(
            Message(speaker="coordinator", content="the repair moves to Tuesday")
        )

        then = memory.replay(up_to_seq=first.seq)
        now = memory.replay()
        print("in memory at the first recall:", len(then.visible_messages), "items")
        print("in memory now:", [m.content for m in now.visible_messages])
        print("recall counts:", [s.num_recalled for s in now.recall_stats.values()])
