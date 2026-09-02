# BEDA Test 2 — Controlled Build

## What It Does

This is a small, runnable enquiry intelligence prototype for the supplied fictional BEDA pack. It imports 12 enquiries, preserves raw evidence, produces a validated structured analysis, finds CRM and duplicate candidates, routes only to supplied staff, creates a local review queue, and records an audit trail. It never sends a message or changes a live CRM.

## Architecture

```text
Synthetic Data Pack -> Loader + Validation -> Raw SQLite persistence
                                      -> attachment resolver
                                      -> structured analysis adapter
                                      -> deterministic matching + routing
                                      -> approval gate -> audit log -> inspection UI
```

## Why This Architecture

The prototype keeps ambiguity in the analysis adapter and keeps correctness, identity matching, routing, state changes, and audit records deterministic. SQLite and a synchronous local flow make the behaviour easy to inspect and demonstrate.

## Data Pack

`data/` preserves the supplied fictional BEDA source inputs, including the original email `from` key. The loader maps that safely to the internal `from_raw` field, preserves raw CRM rows, and conservatively realigns C002's trailing fields because its phone is missing.

## Untrusted Input Policy

All email, attachment, CRM, and staff content is treated only as untrusted data. The analysis prompt prohibits following input instructions, executing commands, calling URLs, exposing secrets, contacting services, or changing policy. Only evidence-backed facts are extracted; unknown facts are null.

## AI vs Deterministic Logic

The default local mode uses a deterministic, content-driven mock analyzer so the project can be reviewed without external credentials. It derives classification, extraction, uncertainty, and drafts from the subject, sender, body, and text attachment; it is not an LLM and does not use email IDs. An optional Gemini structured-output adapter is available behind the same interface. AI is reserved for ambiguous reasoning; deterministic application code retains authority over matching, routing, permissions, approval, persistence, and auditability. Fixture counts are separate from team size, unsynchronised CRM-record counts are separate from people counts, and billing-period consumption is separate from annual consumption.

## Classification Categories

The supported categories are sales opportunity, support, billing, technical, partner coordination, job application, internal alert, contact correction, junk, and unknown. Every imported email has a category, confidence, recommendation, explicit gaps, and uncertainty where applicable.

## CRM Matching

Candidate scores use normalized email, phone, email domain, contact name, company, and relevant service context. Scores are capped at 1.0 and labelled strong, possible, or weak. Candidates are never auto-merged.

## Duplicate Detection

The deterministic signals include sender email, phone, company, contact name, shared sales intent, and explicit correction language. E001/E002 and E009/E010 are visible as candidates, while their raw records remain separate.

## Staff Routing

Routing only uses the supplied directory: Matt for major/multi-site commercial work, Zidane for normal inbound sales, Ties for operational triage, and Ali for system incidents. No engineer, HR owner, or other staff member is invented.

## Human Approval

All non-junk recommendations require approval. Approval or rejection changes only local prototype state and adds an audit event. It does not send email, update CRM identity data, merge records, change invoices, approve a refund, offer pricing, or confirm project go-ahead.

## Auditability

The inspector exposes source input and attachment, analysis outcome, scores and reasons, routing, draft, review state, and chronological audit trail. Audit events include loading, parsing, analysis, candidate discovery, routing, draft creation, approval requirement, and human decisions.

## Failure Handling

Raw inputs are persisted before analysis. If a provider or schema boundary fails, the record and attachment are retained, marked `ai_failed`, and an approval-required audit record is created with no side effect. Gemini retries only temporary HTTP/network failures and is bounded by `MAX_MODEL_RETRIES` (default 2); invalid credentials, malformed output, and schema errors are not retried.

## Security

`.env` is ignored; `.env.example` contains placeholders only. The UI never receives an API key. This project uses only fictional data and has no outbound integration.

## Cost and Latency

The local pack is analyzed once per email, attachments are read locally, and matching is deterministic. There are no agents, embeddings, vector database, queue, autonomous calls, or network dependency in mock mode.

## Setup

Requires Python 3.11+.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Run

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Click **Import data pack**; repeated import is safe and idempotent.

## Demo Walkthrough

Show E001 for the bill attachment, C001 match, E002 duplicate and Matt route; E003 for the $2,640 discrepancy; E009/E010 for the correction approval gate; E011 for Ali; then the warning panel and an audit timeline.

## Tests

```powershell
pytest -q
```

## AI Tools / Models Used

Python/FastAPI implementation with a credential-free deterministic content-driven mock analyzer. The configuration includes an optional Gemini Flash-Lite structured-output adapter, but it has not been live-verified because this repository contains no credentials.

## Known Weaknesses

The dataset is small and candidate scoring is deterministic. The optional Gemini adapter has not been live-verified with credentials. There is no production CRM connector, outbound sender, background queue, binary/PDF attachment parser, or vector similarity. C002 recovery is a documented heuristic, and staff routing is necessarily limited to the supplied directory.

## What I Would Improve With Another Day

Migrate to PostgreSQL, add a background queue, richer attachment parsing, a model evaluation dataset, a live CRM sandbox, observability, confidence calibration, reviewer correction feedback, stronger entity resolution, semantic matching only as a secondary candidate signal, and role-based approval permissions.
