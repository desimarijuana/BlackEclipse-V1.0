"""Evidence store — persistence for the web research engine.

Bound to the ONE `AgentMemoryStore` sqlite connection (`agent-memory.db`), the
same pattern as `browser/store.py`, `jobs/store.py` and `code/store.py`. It owns
only its own tables; the DDL is idempotent (`CREATE TABLE IF NOT EXISTS`). NEVER
`jdds.db` and NEVER `eclipse-memory.db`.

Persisted entities: research runs, questions, plans, tasks, sources, evidence,
claims, claim↔evidence links, citations, conflicts, validation results and
immutable snapshots. Indexed on the identifiers a run actually queries by.

Raw artifacts are NOT stored here; only bounded, content-free-enough structured
rows. Large raw text belongs to the existing artifact/file storage.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS WebResearchRun (
  researchId   TEXT PRIMARY KEY,
  question     TEXT NOT NULL,
  objective    TEXT,
  intent       TEXT,
  depth        TEXT,
  state        TEXT NOT NULL,
  pointInTime  TEXT,
  freshness    TEXT,
  createdAt    TEXT NOT NULL,
  updatedAt    TEXT NOT NULL,
  mandate      TEXT,
  plan         TEXT,
  status       TEXT
);
CREATE INDEX IF NOT EXISTS idx_wrr_state ON WebResearchRun(state);
CREATE INDEX IF NOT EXISTS idx_wrr_created ON WebResearchRun(createdAt);

CREATE TABLE IF NOT EXISTS WebResearchQuestion (
  id           TEXT PRIMARY KEY,
  researchId   TEXT NOT NULL,
  question     TEXT NOT NULL,
  intent       TEXT,
  required     INTEGER NOT NULL DEFAULT 1,
  answered     INTEGER NOT NULL DEFAULT 0,
  notes        TEXT
);
CREATE INDEX IF NOT EXISTS idx_wrq_research ON WebResearchQuestion(researchId);

CREATE TABLE IF NOT EXISTS WebResearchSource (
  sourceId     TEXT PRIMARY KEY,
  researchId   TEXT,
  canonicalUrl TEXT NOT NULL,
  domain       TEXT,
  publisher    TEXT,
  sourceType   TEXT,
  authority    TEXT,
  publishedAt  TEXT,
  retrievedAt  TEXT,
  familyId     TEXT,
  contentHash  TEXT,
  ranking      REAL
);
CREATE INDEX IF NOT EXISTS idx_wrs_research ON WebResearchSource(researchId);
CREATE INDEX IF NOT EXISTS idx_wrs_domain ON WebResearchSource(domain);
CREATE INDEX IF NOT EXISTS idx_wrs_hash ON WebResearchSource(contentHash);

CREATE TABLE IF NOT EXISTS WebResearchEvidence (
  evidenceId   TEXT PRIMARY KEY,
  researchId   TEXT,
  sourceId     TEXT,
  sourceUrl    TEXT,
  sourceType   TEXT,
  entityId     TEXT,
  publishedAt  TEXT,
  updatedAt    TEXT,
  effectiveAt  TEXT,
  knownAt      TEXT,
  retrievedAt  TEXT,
  documentId   TEXT,
  page         INTEGER,
  section      TEXT,
  rawText      TEXT,
  claimText    TEXT,
  structuredValue TEXT,
  unit         TEXT,
  period       TEXT,
  contentHash  TEXT,
  confidence   REAL,
  contentTrust TEXT,
  provenance   TEXT
);
CREATE INDEX IF NOT EXISTS idx_wre_research ON WebResearchEvidence(researchId);
CREATE INDEX IF NOT EXISTS idx_wre_source ON WebResearchEvidence(sourceId);
CREATE INDEX IF NOT EXISTS idx_wre_entity ON WebResearchEvidence(entityId);
CREATE INDEX IF NOT EXISTS idx_wre_hash ON WebResearchEvidence(contentHash);

CREATE TABLE IF NOT EXISTS WebResearchClaim (
  id           TEXT PRIMARY KEY,
  researchId   TEXT NOT NULL,
  text         TEXT NOT NULL,
  kind         TEXT,
  status       TEXT,
  confidence   REAL,
  calculationId TEXT,
  issues       TEXT,
  createdAt    TEXT
);
CREATE INDEX IF NOT EXISTS idx_wrc_research ON WebResearchClaim(researchId);
CREATE INDEX IF NOT EXISTS idx_wrc_status ON WebResearchClaim(status);

CREATE TABLE IF NOT EXISTS WebResearchClaimEvidence (
  claimId      TEXT NOT NULL,
  evidenceId   TEXT NOT NULL,
  relation     TEXT,
  PRIMARY KEY (claimId, evidenceId, relation)
);

CREATE TABLE IF NOT EXISTS WebResearchCitation (
  citationId   TEXT PRIMARY KEY,
  researchId   TEXT,
  claimId      TEXT,
  evidenceId   TEXT,
  sourceUrl    TEXT,
  title        TEXT,
  section      TEXT,
  page         INTEGER,
  locator      TEXT,
  createdAt    TEXT
);
CREATE INDEX IF NOT EXISTS idx_wrci_research ON WebResearchCitation(researchId);
CREATE INDEX IF NOT EXISTS idx_wrci_claim ON WebResearchCitation(claimId);

CREATE TABLE IF NOT EXISTS WebResearchConflict (
  id             TEXT PRIMARY KEY,
  researchId     TEXT,
  metric         TEXT,
  period         TEXT,
  status         TEXT,
  material       INTEGER,
  explanation    TEXT,
  candidates     TEXT,
  createdAt      TEXT
);
CREATE INDEX IF NOT EXISTS idx_wrconf_research ON WebResearchConflict(researchId);

CREATE TABLE IF NOT EXISTS WebResearchValidation (
  id           TEXT PRIMARY KEY,
  researchId   TEXT,
  claimId      TEXT,
  status       TEXT,
  issues       TEXT,
  createdAt    TEXT
);
CREATE INDEX IF NOT EXISTS idx_wrv_research ON WebResearchValidation(researchId);

CREATE TABLE IF NOT EXISTS WebResearchSnapshot (
  snapshotId   TEXT PRIMARY KEY,
  researchId   TEXT NOT NULL,
  version      INTEGER NOT NULL,
  createdAt    TEXT NOT NULL,
  payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wrsnap_research ON WebResearchSnapshot(researchId);

-- A source or evidence artifact is IDENTIFIED by its URL/content (sourceId,
-- evidenceId) but BELONGS to one or more research runs. These link tables make
-- that many-to-many explicit, so the same URL fetched in two runs is attributed
-- to both and never clobbered. The `researchId` column on the parent rows is kept
-- as the most-recent run for backward compatibility; the link table is
-- authoritative for membership.
CREATE TABLE IF NOT EXISTS WebResearchSourceLink (
  researchId   TEXT NOT NULL,
  sourceId     TEXT NOT NULL,
  PRIMARY KEY (researchId, sourceId)
);
CREATE INDEX IF NOT EXISTS idx_wrslink_source ON WebResearchSourceLink(sourceId);

CREATE TABLE IF NOT EXISTS WebResearchEvidenceLink (
  researchId   TEXT NOT NULL,
  evidenceId   TEXT NOT NULL,
  PRIMARY KEY (researchId, evidenceId)
);
CREATE INDEX IF NOT EXISTS idx_wrelink_evidence ON WebResearchEvidenceLink(evidenceId);

CREATE TABLE IF NOT EXISTS WebResearchMeta (
  key    TEXT PRIMARY KEY,
  value  TEXT
);

-- The general entity/knowledge graph (beyond claim→evidence). Every node and
-- edge is ANCHORED to evidence: an entity records the evidence it was mentioned
-- in (`evidenceId`), and a relation records the evidence that supports the edge.
-- No ungrounded node is ever written.
CREATE TABLE IF NOT EXISTS WebResearchEntity (
  entityId     TEXT PRIMARY KEY,
  researchId   TEXT,
  name         TEXT NOT NULL,
  kind         TEXT,
  aliases      TEXT,
  evidenceId   TEXT,
  sourceUrl    TEXT,
  confidence   REAL,
  createdAt    TEXT
);
CREATE INDEX IF NOT EXISTS idx_wre2_research ON WebResearchEntity(researchId);
CREATE INDEX IF NOT EXISTS idx_wre2_name ON WebResearchEntity(name);
CREATE INDEX IF NOT EXISTS idx_wre2_kind ON WebResearchEntity(kind);

CREATE TABLE IF NOT EXISTS WebResearchRelation (
  id           TEXT PRIMARY KEY,
  researchId   TEXT,
  subjectId    TEXT NOT NULL,
  predicate    TEXT NOT NULL,
  objectId     TEXT,
  objectValue  TEXT,
  unit         TEXT,
  period       TEXT,
  evidenceId   TEXT,
  sourceUrl    TEXT,
  confidence   REAL,
  createdAt    TEXT
);
CREATE INDEX IF NOT EXISTS idx_wrrr_research ON WebResearchRelation(researchId);
CREATE INDEX IF NOT EXISTS idx_wrrr_subject ON WebResearchRelation(subjectId);
CREATE INDEX IF NOT EXISTS idx_wrrr_predicate ON WebResearchRelation(predicate);
"""


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _coerce_evidence_row(data: dict[str, Any]) -> dict[str, Any]:
    """Make a stored evidence row safe to hand to `Evidence(**row)`.

    A legacy/partial row may have NULL columns; the model requires `sourceId`,
    `sourceType`, `retrievedAt`, `confidence`, `contentTrust` and an object
    `provenance`. Coerce those to honest, non-fabricated defaults (a missing
    sourceType is `unknown`; a missing timestamp is empty, never invented).
    """
    data["structuredValue"] = _loads(data.get("structuredValue"))
    data["provenance"] = _loads(data.get("provenance")) or {}
    data["sourceId"] = data.get("sourceId") or ""
    data["sourceType"] = data.get("sourceType") or "unknown"
    data["retrievedAt"] = data.get("retrievedAt") or ""
    data["confidence"] = data.get("confidence") if data.get("confidence") is not None else 0.0
    data["contentTrust"] = data.get("contentTrust") or "UNTRUSTED"
    data["rawText"] = data.get("rawText") or ""
    data["contentHash"] = data.get("contentHash") or ""
    return data


class EvidenceStore:
    """Persistence for web research runs and their evidence graph."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        # Backfill legacy rows into the link tables ONCE per database, tracked by a
        # dedicated marker table (self-contained; never touches another
        # subsystem's schema state).
        marker = self._db.execute(
            "SELECT value FROM WebResearchMeta WHERE key = 'linkBackfill'"
        ).fetchone()
        if marker is None:
            self._backfill_links()
            self._db.execute(
                "INSERT OR REPLACE INTO WebResearchMeta (key, value) VALUES ('linkBackfill', '1')"
            )
        self._db.commit()

    def _backfill_links(self) -> None:
        """One-time, idempotent migration of rows that predate the link tables.

        An existing row carries a `researchId`; that is the run it belonged to.
        Copy it into the link table (INSERT OR IGNORE) so old runs remain
        queryable and no data is lost.
        """
        try:
            self._db.execute(
                "INSERT OR IGNORE INTO WebResearchSourceLink (researchId, sourceId) "
                "SELECT researchId, sourceId FROM WebResearchSource WHERE researchId IS NOT NULL"
            )
            self._db.execute(
                "INSERT OR IGNORE INTO WebResearchEvidenceLink (researchId, evidenceId) "
                "SELECT researchId, evidenceId FROM WebResearchEvidence WHERE researchId IS NOT NULL"
            )
        except Exception:  # noqa: BLE001 - backfill must never block boot
            pass

    # ── Runs ───────────────────────────────────────────────────────────────────
    def save_run(self, run: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO WebResearchRun
                 (researchId, question, objective, intent, depth, state, pointInTime,
                  freshness, createdAt, updatedAt, mandate, plan, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(researchId) DO UPDATE SET
                 state=excluded.state, updatedAt=excluded.updatedAt,
                 mandate=excluded.mandate, plan=excluded.plan, status=excluded.status""",
            (
                run["researchId"], run.get("question", ""), run.get("objective"),
                run.get("intent"), run.get("depth"), run.get("state", "PLANNING"),
                run.get("pointInTime"), run.get("freshness"),
                run.get("createdAt") or now_iso(), run.get("updatedAt") or now_iso(),
                _json(run.get("mandate")), _json(run.get("plan")), run.get("status"),
            ),
        )
        self._db.commit()

    def get_run(self, research_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM WebResearchRun WHERE researchId = ?", (research_id,)
        ).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["mandate"] = _loads(data.get("mandate"))
        data["plan"] = _loads(data.get("plan"))
        return data

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchRun ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── Questions ──────────────────────────────────────────────────────────────
    def save_question(self, research_id: str, q: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO WebResearchQuestion (id, researchId, question, intent, required, answered, notes)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET answered=excluded.answered, notes=excluded.notes""",
            (
                q["id"], research_id, q.get("question", ""), q.get("intent"),
                1 if q.get("required", True) else 0, 1 if q.get("answered") else 0,
                _json(q.get("notes")),
            ),
        )
        self._db.commit()

    def list_questions(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchQuestion WHERE researchId = ?", (research_id,)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── Sources ─────────────────────────────────────────────────────────────────
    def save_source(self, source: dict[str, Any], *, research_id: Optional[str] = None, ranking: Optional[float] = None) -> None:
        self._db.execute(
            """INSERT INTO WebResearchSource
                 (sourceId, researchId, canonicalUrl, domain, publisher, sourceType, authority,
                  publishedAt, retrievedAt, familyId, contentHash, ranking)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(sourceId) DO UPDATE SET
                 ranking=COALESCE(excluded.ranking, WebResearchSource.ranking),
                 publishedAt=COALESCE(excluded.publishedAt, WebResearchSource.publishedAt)""",
            (
                source["sourceId"], research_id, source.get("canonicalUrl", ""), source.get("domain"),
                source.get("publisher"), source.get("sourceType"), source.get("authority"),
                source.get("publishedAt"), source.get("retrievedAt"), source.get("sourceFamily"),
                source.get("contentHash"), ranking,
            ),
        )
        if research_id:
            self._db.execute(
                "INSERT OR IGNORE INTO WebResearchSourceLink (researchId, sourceId) VALUES (?, ?)",
                (research_id, source["sourceId"]),
            )
        self._db.commit()

    def list_sources(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT s.* FROM WebResearchSource s "
            "JOIN WebResearchSourceLink l ON l.sourceId = s.sourceId "
            "WHERE l.researchId = ?",
            (research_id,),
        ).fetchall()
        return [_row(r) for r in rows]

    def get_source(self, source_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM WebResearchSource WHERE sourceId = ?", (source_id,)
        ).fetchone()
        return _row(row) if row else None

    def delete_source(self, source_id: str) -> None:
        """Invalidate a source and every run-membership of it."""
        self._db.execute("DELETE FROM WebResearchSource WHERE sourceId = ?", (source_id,))
        self._db.execute("DELETE FROM WebResearchSourceLink WHERE sourceId = ?", (source_id,))
        self._db.commit()

    def unlink_source(self, research_id: str, source_id: str) -> None:
        """Remove a source from ONE run without destroying it for other runs."""
        self._db.execute(
            "DELETE FROM WebResearchSourceLink WHERE researchId = ? AND sourceId = ?",
            (research_id, source_id),
        )
        self._db.commit()

    # ── Evidence ────────────────────────────────────────────────────────────────
    def save_evidence(self, ev: dict[str, Any], *, research_id: Optional[str] = None) -> None:
        self._db.execute(
            """INSERT INTO WebResearchEvidence
                 (evidenceId, researchId, sourceId, sourceUrl, sourceType, entityId, publishedAt,
                  updatedAt, effectiveAt, knownAt, retrievedAt, documentId, page, section, rawText,
                  claimText, structuredValue, unit, period, contentHash, confidence, contentTrust, provenance)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(evidenceId) DO UPDATE SET
                 knownAt=COALESCE(excluded.knownAt, WebResearchEvidence.knownAt),
                 confidence=excluded.confidence,
                 rawText=excluded.rawText""",
            (
                ev["evidenceId"], research_id, ev.get("sourceId"), ev.get("sourceUrl"),
                ev.get("sourceType"), ev.get("entityId"), ev.get("publishedAt"), ev.get("updatedAt"),
                ev.get("effectiveAt"), ev.get("knownAt"), ev.get("retrievedAt"), ev.get("documentId"),
                ev.get("page"), ev.get("section"), ev.get("rawText", ""), ev.get("claimText"),
                _json(ev.get("structuredValue")), ev.get("unit"), ev.get("period"),
                ev.get("contentHash"), ev.get("confidence", 0.0), ev.get("contentTrust", "UNTRUSTED"),
                _json(ev.get("provenance")),
            ),
        )
        if research_id:
            self._db.execute(
                "INSERT OR IGNORE INTO WebResearchEvidenceLink (researchId, evidenceId) VALUES (?, ?)",
                (research_id, ev["evidenceId"]),
            )
        self._db.commit()

    def save_evidence_bulk(self, items: list[dict[str, Any]], *, research_id: Optional[str] = None) -> None:
        for ev in items:
            self.save_evidence(ev, research_id=research_id)

    def list_evidence(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT e.* FROM WebResearchEvidence e "
            "JOIN WebResearchEvidenceLink l ON l.evidenceId = e.evidenceId "
            "WHERE l.researchId = ?",
            (research_id,),
        ).fetchall()
        out = []
        for r in rows:
            data = _coerce_evidence_row(_row(r))
            out.append(data)
        return out

    def delete_evidence(self, evidence_id: str) -> None:
        """Invalidate evidence and every run-membership of it."""
        self._db.execute("DELETE FROM WebResearchEvidence WHERE evidenceId = ?", (evidence_id,))
        self._db.execute("DELETE FROM WebResearchEvidenceLink WHERE evidenceId = ?", (evidence_id,))
        self._db.commit()

    def unlink_evidence(self, research_id: str, evidence_id: str) -> None:
        """Remove evidence from ONE run without destroying it for other runs."""
        self._db.execute(
            "DELETE FROM WebResearchEvidenceLink WHERE researchId = ? AND evidenceId = ?",
            (research_id, evidence_id),
        )
        self._db.commit()

    # ── Claims / links / validations ─────────────────────────────────────────────
    def save_claim(self, research_id: str, claim: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO WebResearchClaim (id, researchId, text, kind, status, confidence, calculationId, issues, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status, issues=excluded.issues, confidence=excluded.confidence""",
            (
                claim["id"], research_id, claim.get("text", ""), claim.get("kind", "FACT"),
                claim.get("status", "UNSUPPORTED"), claim.get("confidence", 0.0),
                claim.get("calculationId"), _json(claim.get("issues")), claim.get("createdAt") or now_iso(),
            ),
        )
        self._db.commit()

    def link_claim_evidence(self, claim_id: str, evidence_id: str, relation: str = "supports") -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO WebResearchClaimEvidence (claimId, evidenceId, relation) VALUES (?,?,?)",
            (claim_id, evidence_id, relation),
        )
        self._db.commit()

    def save_validation(self, research_id: str, claim_id: str, status: str, issues: list[str]) -> None:
        self._db.execute(
            "INSERT INTO WebResearchValidation (id, researchId, claimId, status, issues, createdAt) VALUES (?,?,?,?,?,?)",
            (f"v_{claim_id}_{now_iso()}", research_id, claim_id, status, _json(issues), now_iso()),
        )
        self._db.commit()

    def list_claims(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchClaim WHERE researchId = ?", (research_id,)
        ).fetchall()
        return [_row(r) for r in rows]

    def list_claim_evidence(self, claim_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchClaimEvidence WHERE claimId = ?", (claim_id,)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── Citations ───────────────────────────────────────────────────────────────
    def save_citation(self, research_id: str, citation: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO WebResearchCitation
                 (citationId, researchId, claimId, evidenceId, sourceUrl, title, section, page, locator, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                citation["citationId"], research_id, citation.get("claimId"), citation.get("evidenceId"),
                citation.get("sourceUrl"), citation.get("title"), citation.get("section"),
                citation.get("page"), citation.get("locator"), now_iso(),
            ),
        )
        self._db.commit()

    def list_citations(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchCitation WHERE researchId = ?", (research_id,)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── Conflicts ───────────────────────────────────────────────────────────────
    def save_conflict(self, research_id: str, conflict: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO WebResearchConflict (id, researchId, metric, period, status, material, explanation, candidates, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                conflict.get("id") or f"c_{len(self.list_conflicts(research_id)) + 1}",
                research_id, conflict.get("metric"), conflict.get("period"), conflict.get("status"),
                1 if conflict.get("material", True) else 0, conflict.get("explanation"),
                _json(conflict.get("candidates")), now_iso(),
            ),
        )
        self._db.commit()

    def list_conflicts(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchConflict WHERE researchId = ?", (research_id,)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── Snapshots ────────────────────────────────────────────────────────────────
    def create_snapshot(self, research_id: str, payload: dict[str, Any]) -> str:
        existing = self._db.execute(
            "SELECT COUNT(*) AS n FROM WebResearchSnapshot WHERE researchId = ?", (research_id,)
        ).fetchone()
        version = int(existing["n"] if existing else 0) + 1
        snapshot_id = f"{research_id}_v{version}"
        self._db.execute(
            "INSERT INTO WebResearchSnapshot (snapshotId, researchId, version, createdAt, payload) VALUES (?,?,?,?,?)",
            (snapshot_id, research_id, version, now_iso(), _json(payload)),
        )
        self._db.commit()
        return snapshot_id

    def list_snapshots(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchSnapshot WHERE researchId = ? ORDER BY version ASC", (research_id,)
        ).fetchall()
        out = []
        for r in rows:
            data = _row(r)
            data["payload"] = _loads(data.get("payload"))
            out.append(data)
        return out

    def get_snapshot(self, research_id: str, version: Optional[int] = None) -> Optional[dict[str, Any]]:
        if version is None:
            row = self._db.execute(
                "SELECT * FROM WebResearchSnapshot WHERE researchId = ? ORDER BY version DESC LIMIT 1",
                (research_id,),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT * FROM WebResearchSnapshot WHERE researchId = ? AND version = ?",
                (research_id, version),
            ).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["payload"] = _loads(data.get("payload"))
        return data

    # ── Entity / knowledge graph ─────────────────────────────────────────────────
    def save_entity(self, entity: dict[str, Any], research_id: Optional[str] = None) -> None:
        """Upsert an evidence-anchored entity. `evidenceId` is required so no
        ungrounded node is written."""
        self._db.execute(
            """INSERT INTO WebResearchEntity
                 (entityId, researchId, name, kind, aliases, evidenceId, sourceUrl, confidence, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(entityId) DO UPDATE SET
                 researchId=excluded.researchId, name=excluded.name, kind=excluded.kind,
                 aliases=excluded.aliases, evidenceId=excluded.evidenceId,
                 sourceUrl=excluded.sourceUrl, confidence=excluded.confidence""",
            (
                entity["entityId"], research_id, entity.get("name", ""), entity.get("kind"),
                _json(entity.get("aliases")), entity.get("evidenceId"), entity.get("sourceUrl"),
                entity.get("confidence"), now_iso(),
            ),
        )
        self._db.commit()

    def save_relation(self, relation: dict[str, Any], research_id: Optional[str] = None) -> None:
        """Upsert an evidence-anchored relation edge. `evidenceId` records the
        evidence that supports the edge."""
        self._db.execute(
            """INSERT OR REPLACE INTO WebResearchRelation
                 (id, researchId, subjectId, predicate, objectId, objectValue, unit, period,
                  evidenceId, sourceUrl, confidence, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                relation["id"], research_id, relation.get("subjectId"), relation.get("predicate"),
                relation.get("objectId"), relation.get("objectValue"), relation.get("unit"),
                relation.get("period"), relation.get("evidenceId"), relation.get("sourceUrl"),
                relation.get("confidence"), now_iso(),
            ),
        )
        self._db.commit()

    def list_entities(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchEntity WHERE researchId = ?", (research_id,)
        ).fetchall()
        out = []
        for r in rows:
            data = _row(r)
            data["aliases"] = _loads(data.get("aliases"))
            out.append(data)
        return out

    def list_relations(self, research_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WebResearchRelation WHERE researchId = ?", (research_id,)
        ).fetchall()
        return [_row(r) for r in rows]

    def find_entity(self, name: str) -> list[dict[str, Any]]:
        """Entities across runs matching a name (exact, case-insensitive)."""
        rows = self._db.execute(
            "SELECT * FROM WebResearchEntity WHERE lower(name) = lower(?)", (name,)
        ).fetchall()
        out = []
        for r in rows:
            data = _row(r)
            data["aliases"] = _loads(data.get("aliases"))
            out.append(data)
        return out


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return None


def _loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


__all__ = ["EvidenceStore"]
