"""Persistence for quantitative research.

One rule: this module NEVER opens a database. It uses the ONE
`agent-memory.db` connection owned by `QuantStore` and adds its own idempotent,
additive DDL. Large documents and reports live in the Artifact Center; this
module stores metadata, specifications and lineage.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Optional

from ..errors import QuantError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS QuantLiterature (
  id TEXT PRIMARY KEY,
  researchId TEXT,
  sourceId TEXT,
  doi TEXT,
  arxivId TEXT,
  openalexId TEXT,
  s2Id TEXT,
  title TEXT NOT NULL,
  authorsJson TEXT,
  year INTEGER,
  venue TEXT,
  abstract TEXT,
  url TEXT,
  pdfUrl TEXT,
  license TEXT,
  accessStatus TEXT,
  isOpenAccess INTEGER NOT NULL DEFAULT 0,
  referencesJson TEXT,
  contentHash TEXT,
  createdAt TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_qlit_doi ON QuantLiterature(doi);
CREATE INDEX IF NOT EXISTS idx_qlit_research ON QuantLiterature(researchId);
CREATE INDEX IF NOT EXISTS idx_qlit_arxiv ON QuantLiterature(arxivId);

CREATE TABLE IF NOT EXISTS QuantMethodRelationship (
  id TEXT PRIMARY KEY,
  fromMethodId TEXT NOT NULL,
  toMethodId TEXT NOT NULL,
  relation TEXT NOT NULL,
  note TEXT,
  literatureId TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qmr_from ON QuantMethodRelationship(fromMethodId);

CREATE TABLE IF NOT EXISTS QuantMethodPaper (
  methodId TEXT NOT NULL,
  literatureId TEXT NOT NULL,
  role TEXT NOT NULL,
  PRIMARY KEY (methodId, literatureId, role)
);

CREATE TABLE IF NOT EXISTS QuantMethodImplementation (
  id TEXT PRIMARY KEY,
  methodId TEXT NOT NULL,
  version TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT 'python',
  codeArtifactId TEXT,
  workerRunId TEXT,
  testStatus TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qmi_method ON QuantMethodImplementation(methodId);

CREATE TABLE IF NOT EXISTS QuantReproduction (
  id TEXT PRIMARY KEY,
  methodId TEXT NOT NULL,
  implementationId TEXT,
  datasetId TEXT,
  datasetVersion TEXT,
  experimentId TEXT,
  publishedBenchmarkJson TEXT,
  observedMetricsJson TEXT,
  fidelityJson TEXT,
  validationJson TEXT,
  status TEXT NOT NULL,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qrep_method ON QuantReproduction(methodId);

CREATE TABLE IF NOT EXISTS QuantResearchDossier (
  id TEXT PRIMARY KEY,
  sessionId TEXT,
  researchId TEXT,
  title TEXT NOT NULL,
  question TEXT NOT NULL,
  status TEXT NOT NULL,
  artifactId TEXT,
  dossierJson TEXT NOT NULL,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qdossier_session ON QuantResearchDossier(sessionId);
"""


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, ensure_ascii=False)


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _ident(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class ResearchStore:
    """Metadata repository for literature, method specs and research lineage."""

    def __init__(self, quant_store: Any) -> None:
        if quant_store is None:
            raise QuantError("the quant store is not configured")
        self._quant = quant_store
        self._db = quant_store._db
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        # Extend the ONE QuantMethod table rather than duplicating it.
        self._ensure_column("QuantReproduction", "validationJson", "TEXT")
        self._ensure_column("QuantLiterature", "isOpenAccess", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("QuantLiterature", "referencesJson", "TEXT")
        for column, ddl in (
            ("version", "TEXT"),
            ("aliasesJson", "TEXT"),
            ("objectiveJson", "TEXT"),
            ("mathSpecJson", "TEXT"),
            ("inputsJson", "TEXT"),
            ("parametersJson", "TEXT"),
            ("assumptionsJson", "TEXT"),
            ("limitationsJson", "TEXT"),
            ("provenanceJson", "TEXT"),
            ("implementationStatus", "TEXT"),
            ("reproductionStatus", "TEXT"),
            ("lifecycleStatus", "TEXT"),
            ("confidence", "TEXT"),
            ("contentHash", "TEXT"),
        ):
            self._ensure_column("QuantMethod", column, ddl)
        self._db.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # ── literature ───────────────────────────────────────────────────────────

    def save_literature(self, record: dict[str, Any]) -> dict[str, Any]:
        title = str(record.get("title") or "").strip()
        if not title:
            raise QuantError("a literature record needs a title")
        doi = (str(record.get("doi") or "").strip().lower() or None)
        arxiv = (str(record.get("arxivId") or "").strip() or None)
        existing = None
        if doi:
            existing = self._db.execute(
                "SELECT * FROM QuantLiterature WHERE doi=?", (doi,)
            ).fetchone()
        if existing is None and arxiv:
            existing = self._db.execute(
                "SELECT * FROM QuantLiterature WHERE arxivId=?", (arxiv,)
            ).fetchone()
        if existing is not None:
            lit_id = existing["id"]
            self._db.execute(
                "UPDATE QuantLiterature SET researchId=COALESCE(?,researchId), "
                "sourceId=COALESCE(?,sourceId), doi=COALESCE(?,doi), "
                "arxivId=COALESCE(?,arxivId), openalexId=COALESCE(?,openalexId), "
                "s2Id=COALESCE(?,s2Id), title=?, authorsJson=COALESCE(?,authorsJson), "
                "year=COALESCE(?,year), venue=COALESCE(?,venue), abstract=COALESCE(?,abstract), "
                "url=COALESCE(?,url), pdfUrl=COALESCE(?,pdfUrl), license=COALESCE(?,license), "
                "accessStatus=COALESCE(?,accessStatus), "
                "isOpenAccess=MAX(isOpenAccess,?), referencesJson=COALESCE(?,referencesJson), "
                "contentHash=COALESCE(?,contentHash) "
                "WHERE id=?",
                (record.get("researchId"), record.get("sourceId"), doi, arxiv,
                 record.get("openalexId"), record.get("s2Id"), title,
                 _json(record.get("authors")) if record.get("authors") else None,
                 record.get("year"), record.get("venue"), record.get("abstract"),
                 record.get("url"), record.get("pdfUrl"), record.get("license"),
                 record.get("accessStatus"), 1 if record.get("isOpenAccess") else 0,
                 _json(record.get("references")) if record.get("references") else None,
                 record.get("contentHash"), lit_id),
            )
        else:
            lit_id = str(record.get("id") or _ident("lit"))
            self._db.execute(
                "INSERT INTO QuantLiterature "
                "(id,researchId,sourceId,doi,arxivId,openalexId,s2Id,title,authorsJson,"
                "year,venue,abstract,url,pdfUrl,license,accessStatus,isOpenAccess,"
                "referencesJson,contentHash,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lit_id, record.get("researchId"), record.get("sourceId"), doi, arxiv,
                 record.get("openalexId"), record.get("s2Id"), title,
                 _json(record.get("authors")) if record.get("authors") else None,
                 record.get("year"), record.get("venue"), record.get("abstract"),
                 record.get("url"), record.get("pdfUrl"), record.get("license"),
                 record.get("accessStatus"), 1 if record.get("isOpenAccess") else 0,
                 _json(record.get("references")) if record.get("references") else None,
                 record.get("contentHash"), _iso_now()),
            )
        self._db.commit()
        return self.get_literature(lit_id)

    def get_literature(self, literature_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantLiterature WHERE id=?", (literature_id,)
        ).fetchone()
        if row is None:
            raise QuantError(f"literature {literature_id!r} not found",
                             detail={"literatureId": literature_id})
        return self._lit_row(row)

    def find_literature(self, *, query: str = "", doi: str = "",
                        arxiv_id: str = "") -> list[dict[str, Any]]:
        if doi:
            row = self._db.execute(
                "SELECT * FROM QuantLiterature WHERE doi=?", (doi.lower(),)
            ).fetchone()
            return [self._lit_row(row)] if row else []
        if arxiv_id:
            row = self._db.execute(
                "SELECT * FROM QuantLiterature WHERE arxivId=?", (arxiv_id,)
            ).fetchone()
            return [self._lit_row(row)] if row else []
        if not query:
            return self.list_literature()
        like = f"%{query}%"
        rows = self._db.execute(
            "SELECT * FROM QuantLiterature WHERE title LIKE ? OR abstract LIKE ? "
            "ORDER BY year DESC, createdAt DESC LIMIT 50", (like, like),
        ).fetchall()
        return [self._lit_row(r) for r in rows]

    def list_literature(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM QuantLiterature ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._lit_row(r) for r in rows]

    @staticmethod
    def _lit_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "researchId": row["researchId"],
            "sourceId": row["sourceId"],
            "doi": row["doi"],
            "arxivId": row["arxivId"],
            "openalexId": row["openalexId"],
            "s2Id": row["s2Id"],
            "title": row["title"],
            "authors": _loads(row["authorsJson"], []),
            "year": row["year"],
            "venue": row["venue"],
            "abstract": row["abstract"],
            "url": row["url"],
            "pdfUrl": row["pdfUrl"],
            "license": row["license"],
            "accessStatus": row["accessStatus"],
            "isOpenAccess": bool(row["isOpenAccess"]) if "isOpenAccess" in row.keys() else False,
            "references": _loads(row["referencesJson"], []) if "referencesJson" in row.keys() else [],
            "contentHash": row["contentHash"],
            "createdAt": row["createdAt"],
        }

    # ── method specs (the ONE QuantMethod table) ─────────────────────────────

    def save_method_spec(self, spec: dict[str, Any], *,
                         status: str = "discovered") -> dict[str, Any]:
        method_id = str(spec.get("methodId") or "").strip()
        if not method_id:
            raise QuantError("a method spec needs a methodId")
        now = _iso_now()
        digest = _hash(spec)
        existing = self._db.execute(
            "SELECT * FROM QuantMethod WHERE id=?", (method_id,)
        ).fetchone()
        values = (
            spec.get("name") or method_id,
            spec.get("family"),
            status,
            _json(spec),
            _json({"references": spec.get("references") or [],
                   "provenance": spec.get("provenance") or {}}),
            spec.get("strategyId"),
            spec.get("version") or "1.0.0",
            _json(spec.get("aliases") or []),
            _json(spec.get("objective") or []),
            _json(spec.get("mathSpec") or {"equations": spec.get("equations") or []}),
            _json(spec.get("inputs") or []),
            _json(spec.get("parameters") or []),
            _json(spec.get("assumptions") or []),
            _json(spec.get("limitations") or []),
            _json(spec.get("provenance") or {}),
            spec.get("implementationStatus") or "none",
            spec.get("reproductionStatus") or "none",
            spec.get("lifecycleStatus") or "proposed",
            str((spec.get("provenance") or {}).get("confidence") or "low"),
            digest,
        )
        if existing is None:
            self._db.execute(
                "INSERT INTO QuantMethod (id,name,methodFamily,status,specJson,evidenceJson,"
                "strategyId,version,aliasesJson,objectiveJson,mathSpecJson,inputsJson,"
                "parametersJson,assumptionsJson,limitationsJson,provenanceJson,"
                "implementationStatus,reproductionStatus,lifecycleStatus,confidence,"
                "contentHash,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (method_id, *values, now, now),
            )
        else:
            self._db.execute(
                "UPDATE QuantMethod SET name=?,methodFamily=?,status=?,specJson=?,"
                "evidenceJson=?,strategyId=COALESCE(?,strategyId),version=?,aliasesJson=?,"
                "objectiveJson=?,mathSpecJson=?,inputsJson=?,parametersJson=?,"
                "assumptionsJson=?,limitationsJson=?,provenanceJson=?,"
                "implementationStatus=?,reproductionStatus=?,lifecycleStatus=?,"
                "confidence=?,contentHash=?,updatedAt=? WHERE id=?",
                (*values, now, method_id),
            )
        self._db.commit()
        return self.get_method_spec(method_id)

    def get_method_spec(self, method_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantMethod WHERE id=?", (method_id,)
        ).fetchone()
        if row is None:
            raise QuantError(f"method {method_id!r} not found",
                             detail={"methodId": method_id})
        return self._method_row(row)

    def list_method_specs(self, *, family: str | None = None,
                          lifecycle: str | None = None,
                          limit: int = 100) -> list[dict[str, Any]]:
        clauses, args = [], []
        if family:
            clauses.append("methodFamily=?")
            args.append(family)
        if lifecycle:
            clauses.append("lifecycleStatus=?")
            args.append(lifecycle)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM QuantMethod{where} ORDER BY updatedAt DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
        return [self._method_row(r) for r in rows]

    def search_method_specs(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
        like = f"%{query}%"
        rows = self._db.execute(
            "SELECT * FROM QuantMethod WHERE id LIKE ? OR name LIKE ? OR "
            "methodFamily LIKE ? OR aliasesJson LIKE ? OR objectiveJson LIKE ? "
            "ORDER BY name LIMIT ?",
            (like, like, like, like, like, limit),
        ).fetchall()
        return [self._method_row(r) for r in rows]

    def seed_catalog(self) -> int:
        """Insert catalog methods that do not exist yet. Never overwrites research."""
        from .catalog import CATALOG

        inserted = 0
        for spec in CATALOG:
            row = self._db.execute(
                "SELECT id FROM QuantMethod WHERE id=?", (spec["methodId"],)
            ).fetchone()
            if row is None:
                self.save_method_spec(spec, status="discovered")
                inserted += 1
        return inserted

    @staticmethod
    def _method_row(row: Any) -> dict[str, Any]:
        spec = _loads(row["specJson"], {})
        if not isinstance(spec, dict):
            spec = {}
        for key in ("version", "aliasesJson", "objectiveJson", "mathSpecJson",
                    "inputsJson", "parametersJson", "assumptionsJson",
                    "limitationsJson", "provenanceJson", "implementationStatus",
                    "reproductionStatus", "lifecycleStatus", "confidence", "contentHash"):
            column = row[key] if key in row.keys() else None
            if column is not None and column != "":
                target = key[:-4] if key.endswith("Json") else key
                if key.endswith("Json"):
                    spec[target] = _loads(column, [] if target in ("aliases", "inputs", "parameters", "assumptions", "limitations") else {})
                else:
                    spec[target] = column
        spec.setdefault("methodId", row["id"])
        spec.setdefault("name", row["name"])
        spec.setdefault("family", row["methodFamily"])
        return {
            "id": row["id"],
            "methodId": row["id"],
            "name": row["name"],
            "methodFamily": row["methodFamily"],
            "status": row["status"],
            "spec": spec,
            "evidence": _loads(row["evidenceJson"], {}),
            "strategyId": row["strategyId"],
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }

    # ── relationships ────────────────────────────────────────────────────────

    def add_relationship(self, *, from_method: str, to_method: str, relation: str,
                         note: str | None = None,
                         literature_id: str | None = None) -> dict[str, Any]:
        if relation not in ("alternative", "extends", "critiques", "depends_on",
                            "composes_with", "variant_of"):
            raise QuantError(f"unknown relationship {relation!r}")
        rel_id = _ident("rel")
        self._db.execute(
            "INSERT INTO QuantMethodRelationship "
            "(id,fromMethodId,toMethodId,relation,note,literatureId,createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (rel_id, from_method, to_method, relation, note, literature_id, _iso_now()),
        )
        self._db.commit()
        return {"id": rel_id, "fromMethodId": from_method, "toMethodId": to_method,
                "relation": relation, "note": note, "literatureId": literature_id}

    def list_relationships(self, method_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM QuantMethodRelationship WHERE fromMethodId=? OR toMethodId=? "
            "ORDER BY createdAt", (method_id, method_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def link_paper(self, method_id: str, literature_id: str, role: str = "origin") -> None:
        if role not in ("origin", "extension", "critique", "application"):
            role = "application"
        self._db.execute(
            "INSERT OR IGNORE INTO QuantMethodPaper (methodId,literatureId,role) "
            "VALUES (?,?,?)", (method_id, literature_id, role),
        )
        self._db.commit()

    def list_papers(self, method_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM QuantMethodPaper WHERE methodId=?", (method_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── implementations ──────────────────────────────────────────────────────

    def save_implementation(self, *, method_id: str, version: str = "1.0.0",
                            language: str = "python", code_artifact_id: str | None = None,
                            worker_run_id: str | None = None,
                            test_status: str = "none") -> dict[str, Any]:
        impl_id = _ident("impl")
        self._db.execute(
            "INSERT INTO QuantMethodImplementation "
            "(id,methodId,version,language,codeArtifactId,workerRunId,testStatus,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (impl_id, method_id, version, language, code_artifact_id, worker_run_id,
             test_status, _iso_now()),
        )
        self._db.commit()
        return self.get_implementation(impl_id)

    def get_implementation(self, implementation_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantMethodImplementation WHERE id=?", (implementation_id,)
        ).fetchone()
        if row is None:
            raise QuantError(f"implementation {implementation_id!r} not found")
        return dict(row)

    def list_implementations(self, method_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM QuantMethodImplementation WHERE methodId=? ORDER BY createdAt DESC",
            (method_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── reproductions ────────────────────────────────────────────────────────

    def save_reproduction(self, record: dict[str, Any]) -> dict[str, Any]:
        rep_id = str(record.get("id") or _ident("rep"))
        self._db.execute(
            "INSERT INTO QuantReproduction "
            "(id,methodId,implementationId,datasetId,datasetVersion,experimentId,"
            "publishedBenchmarkJson,observedMetricsJson,fidelityJson,status,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rep_id, record.get("methodId"), record.get("implementationId"),
             record.get("datasetId"), record.get("datasetVersion"),
             record.get("experimentId"), _json(record.get("publishedBenchmark")),
             _json(record.get("observedMetrics")), _json(record.get("fidelity")),
             record.get("status") or "inconclusive", _iso_now()),
        )
        self._db.commit()
        return self.get_reproduction(rep_id)

    def get_reproduction(self, reproduction_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantReproduction WHERE id=?", (reproduction_id,)
        ).fetchone()
        if row is None:
            raise QuantError(f"reproduction {reproduction_id!r} not found")
        data = dict(row)
        for key in ("publishedBenchmarkJson", "observedMetricsJson", "fidelityJson",
                    "validationJson"):
            data[key[:-4]] = _loads(row[key], {})
        return data

    def save_validation(self, reproduction_id: str,
                        validation: dict[str, Any]) -> dict[str, Any]:
        self.get_reproduction(reproduction_id)
        self._db.execute(
            "UPDATE QuantReproduction SET validationJson=? WHERE id=?",
            (_json(validation), reproduction_id),
        )
        self._db.commit()
        return self.get_reproduction(reproduction_id)

    def list_reproductions(self, method_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id FROM QuantReproduction WHERE methodId=? ORDER BY createdAt DESC",
            (method_id,),
        ).fetchall()
        return [self.get_reproduction(r["id"]) for r in rows]

    # ── dossiers ─────────────────────────────────────────────────────────────

    def save_dossier(self, record: dict[str, Any]) -> dict[str, Any]:
        dossier_id = str(record.get("id") or _ident("dsr"))
        self._db.execute(
            "INSERT INTO QuantResearchDossier "
            "(id,sessionId,researchId,title,question,status,artifactId,dossierJson,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (dossier_id, record.get("sessionId"), record.get("researchId"),
             record.get("title") or "Quant research dossier",
             record.get("question") or "", record.get("status") or "draft",
             record.get("artifactId"), _json(record.get("dossier") or {}), _iso_now()),
        )
        self._db.commit()
        return self.get_dossier(dossier_id)

    def get_dossier(self, dossier_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantResearchDossier WHERE id=?", (dossier_id,)
        ).fetchone()
        if row is None:
            raise QuantError(f"dossier {dossier_id!r} not found")
        data = dict(row)
        data["dossier"] = _loads(row["dossierJson"], {})
        return data

    def list_dossiers(self, *, session_id: str | None = None,
                      limit: int = 50) -> list[dict[str, Any]]:
        if session_id:
            rows = self._db.execute(
                "SELECT id FROM QuantResearchDossier WHERE sessionId=? "
                "ORDER BY createdAt DESC LIMIT ?", (session_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT id FROM QuantResearchDossier ORDER BY createdAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self.get_dossier(r["id"]) for r in rows]


__all__ = ["ResearchStore"]
