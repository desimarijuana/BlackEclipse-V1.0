"""The code capability — policy authority and, in later phases, its tools.

Phase 0 ships only `policy.py`: the single place a code-policy decision is
made. Nothing in this package executes anything yet. Every later phase
(workspace binding, patch authoring, the command broker, verification) imports
its rules from here rather than re-implementing them.
"""
