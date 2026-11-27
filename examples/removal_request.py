"""A resident asks for something to be removed.

Run from a clone: uv run python examples/removal_request.py
"""

import tempfile

from audit_ready_memory import Memory, Message

with tempfile.TemporaryDirectory() as folder:
    with Memory(f"{folder}/memory") as memory:
        report = memory.add_message(
            Message(
                speaker="resident-a",
                content="the pump on Elm Street is broken, call me on 06 0000 0000",
            )
        )
        memory.add_message(
            Message(speaker="coordinator", content="a mechanic will see the pump")
        )

        _, hits = memory.recall("pump")
        print("recalled before the removal:", [hit.seq for hit in hits])

        memory.delete(
            (report.id,),
            reason="the resident asked to remove the phone number",
            requested_by="resident-a",
        )
        _, hits = memory.recall("pump")
        print("recalled after the removal:", [hit.seq for hit in hits])

        removal = memory.replay().deleted[report.id]
        print(f"removed by event {removal.seq}: {removal.reason}")

        reads = memory.query(
            "MATCH (r:Recall)-[:RECALLED]->(m:MemoryEvent {id: $id}) "
            "RETURN r.seq AS seq ORDER BY seq",
            {"id": str(report.id)},
        )
        print("read by events:", [row["seq"] for row in reads])
        print("original still in the log:", memory.get(report.id) is not None)
