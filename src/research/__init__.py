"""Researcher 2.0 — content discovery pipeline for the Content Intelligence Engine.

Stage 3.2. Implements the discovery half of the intelligence flow:

    DISCOVER -> NORMALIZE -> DEDUPLICATE -> CLASSIFY -> VERIFY -> SCORE -> RANK

The Researcher returns ranked ``ContentCandidate`` aggregates (Stage 3.1
contracts). It does NOT make the final publication decision — future
Strategist 2.0 performs SELECT.

Stage 3.2 boundaries:
- No persistence: candidates are ephemeral within a cycle; no SQLite
  changes, no migrations.
- No legacy-state coupling: this package never reads or writes
  ``data/topic_history.json``.
- No production coupling: NewsHunter, Strategist and ``main.py`` are
  untouched; nothing here is imported by the production pipeline yet.
- Verification (later stage in this package) is provenance/source
  verification only — source authenticity, NOT claim fact-checking.
"""
