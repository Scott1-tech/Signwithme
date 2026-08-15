# CLAUDE.md

Context for Claude Code working in this repository. Read `PROJECT_SPEC.md` for
full detail; this file is the short version plus the rules that must not be
broken.

## What this is

A local-only contract review desk for Grand One LLC, a US trucking motor
carrier. Office staff upload a signed driver contract PDF downloaded from
DocuSign. The app reads the driver's answers, checks them against FMCSA and
formatting rules, reports which pages are wrong, and — after a human approves —
stamps the carrier signature and writes an audit record.

Roughly fifteen contracts a week, about fifty pages each.

## Non-negotiables

These are not preferences. Changing any of them changes what the product is.

1. **No AI or LLM in the decision path.** Every validation is a deterministic
   rule. A hallucinated "looks fine" on a compliance document is worse than no
   check at all.
2. **Local only.** Bind to `127.0.0.1`. Driver Social Security numbers are in
   these files and must not cross a network.
3. **Never persist a full SSN.** Last four plus a salted hash. The full value
   lives only inside the PDF on disk.
4. **Never log field values.** Field keys and rule ids only.
5. **The approve step cannot be removed or defaulted.** An explicit checkbox
   plus a typed name is the legal basis under E-SIGN for stamping the
   signature. Do not "streamline" it.
6. **Approvals are append-only.** No update route, no delete route.
7. **Executed contracts are never edited or deleted.** A correction creates a
   new record linked by `supersedes_id`. FMCSA 391.51 requires retention.
8. **The app never contacts the driver.** It produces a list; a human sends it.
9. **The app never edits driver-attested content.** Employment history, SSN,
   date of birth, and the driver's signature are their statements. Carrier-side
   fields only.
10. **Never commit a real contract PDF.** They contain Social Security numbers.
    Generate synthetic fixtures with PyMuPDF at test time.

## Stack

Backend: Python 3.11+, FastAPI, SQLAlchemy, SQLite, PyMuPDF, pdfplumber, pytest.
Frontend: Next.js 15 App Router, TypeScript strict, Tailwind, shadcn/ui,
TanStack Query.

Python for the backend is fixed — the PDF toolchain has no Node equivalent.

## Commands

```bash
# backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pytest -q

# frontend
cd frontend && npm run dev
npm run typecheck
```

## Conventions

- Rules carry a stable `rule_id` such as `cdl.expired`. Never rename one; other
  things count them.
- Flag messages are shown to the user verbatim. Write plain English someone can
  act on. `CDL expired on 03/01/2025`, not `validation error in field 7`.
- Every flag carries a page number where possible. The page number is the point
  of the product — it is what gets sent to the driver.
- A field the extractor cannot find is an error flag, never a silent skip.
- Tests before rules. `services/rules.py` is the product; it needs full coverage.

## Current state

Update this section as work progresses.

- [ ] Extraction service
- [ ] Rules engine and tests
- [ ] Models and database
- [ ] Stamping service
- [ ] API routes
- [ ] Frontend queue and detail
- [ ] Frontend settings and audit
