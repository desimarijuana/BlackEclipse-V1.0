"""A flood fixture: writes far more output than the cap. Must truncate."""
import sys

line = "x" * 1024
for _ in range(50 * 1024):
    sys.stdout.write(line)
sys.stdout.flush()
sys.exit(0)
