"""Echoes any CRON_SECRET / HARNESS_* from the environment.

In a sandboxed run the environment is scrubbed, so this prints ABSENT for each:
the run's env allowlist carries none of them.
"""
import os

for name in ("CRON_SECRET", "HARNESS_CALLBACK_TOKEN", "OPENAI_API_KEY", "HARNESS_PY_URL"):
    value = os.environ.get(name)
    print(f"{name}={'ABSENT' if value is None else 'PRESENT'}")
