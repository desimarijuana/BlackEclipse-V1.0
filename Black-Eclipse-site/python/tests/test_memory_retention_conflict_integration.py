"""Memory retention + conflict integration (Phase 7).

End-to-end across the real service + the normal runtime lifecycle hook:
  1. create an automatic memory with short retention;
  2. invoke the runtime startup lifecycle (the same hook `main._lifespan` calls);
  3. confirm the retention sweep ran;
  4. verify the memory became expired;
  5. confirm retrieval excludes it;
  6. create an explicit replacement;
  7. verify only the authoritative replacement is recalled.
"""

from __future__ import annotations

import os
import tempfile

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore


def test_lifecycle_sweep_and_authoritative_replacement_end_to_end():
    directory = tempfile.mkdtemp(prefix="be-integ-")
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        # 1. An automatic memory with short retention.
        service.policy.set("retention_days", 30)
        automatic = service.write_memory(
            memory_type="preference", content="I prefer concise answers",
            source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
        )
        assert automatic["authority"] == "automatic"
        assert automatic["expiresAt"] is not None
        # Force it due (simulating elapsed time).
        service.store.update_memory(automatic["id"], expiresAt="2000-01-01T00:00:00.000Z")

        # 2. Invoke the runtime startup lifecycle hook (what main._lifespan calls).
        from harness import service as service_module

        runtime = object.__new__(service_module.AgenticService)
        runtime.memory = service
        result = runtime.run_startup_maintenance()

        # 3. The sweep ran and reports observably.
        assert result["ok"] is True
        assert result["inspected"] == 1
        assert result["expired"] == 1

        # 4. The memory is now expired status (and still auditable).
        assert service.store.get_memory(automatic["id"])["status"] == "expired"
        assert service.store.get_memory(automatic["id"])["statusReason"]
        assert service.retention_status()["lastSweep"]["expired"] == 1

        # 5. Retrieval excludes it.
        before = service.retrieve(query="answer style", actor_scope="user", scope_id="u1")
        assert all(m["id"] != automatic["id"] for m in before.memories)

        # 6. An explicit replacement (clearly the latest intent).
        replacement = service.write_memory(
            memory_type="preference", content="I prefer detailed answers now",
            source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
        )
        assert replacement["authority"] == "explicit"
        assert replacement["status"] == "active"

        # 7. Only the authoritative replacement is recalled.
        after = service.retrieve(query="answer style preference", actor_scope="user", scope_id="u1")
        ids = [m["id"] for m in after.memories]
        assert replacement["id"] in ids
        assert automatic["id"] not in ids
    finally:
        service.close()
