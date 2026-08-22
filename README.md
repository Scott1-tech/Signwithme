# Driver Contract Review Desk

A local-only contract review desk for Grand One LLC, a US trucking motor
carrier.

Office staff upload a signed driver contract PDF downloaded from DocuSign.
The app reads the driver's answers, checks them against FMCSA and formatting
rules, reports which pages are wrong, and — after a human approves — stamps
the carrier signature and writes an audit record.

Roughly fifteen contracts a week, about fifty pages each. Steps that used to
take hours of skilled attention take about two minutes.

`PROJECT_SPEC.md` is the source of truth. `CLAUDE.md` lists the constraints
that must not be broken.

## Quick start

Two terminals.

```bash
# Terminal 1 — backend
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set SSN_SALT
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>.

Before the first real contract, go to **Settings** and do three things: point
the field map at your contract's wording (the probe tool shows you what the
PDF actually says), upload the carrier signature PNG and check where it
lands, and fill in the company details.

## Templates: the short version

The app does not need you to describe where the signature goes. Give it one
contract you have **already signed correctly**, and it reads the positions
off that:

1. **Signatures** — save the signature images, by name. More than one person
   can sign, so you pick whose signature to use each time.
2. **Templates** — upload a finished, counter-signed contract. The app finds
   the signature and the date beside it, shows you where, and you confirm.
3. **Upload** — choose a template, a signature, and the date to write. The
   new contract is stamped in exactly the places the finished one had them.
4. **Completed** — every signed contract, with the template and signature
   used, ready to download.

Only dates sitting beside a signature are picked up. A contract is full of
the driver's own dates — date of birth, licence expiry, employment spans —
and writing over one of those would change what the driver attested to.

## How it works

```
DocuSign (driver signs)
   │  reviewer downloads the completed PDF
   ▼
Upload ──► Extract ──► Validate ──► Review queue
                                        │
                          errors? reviewer sends the page-numbered
                          note out of band, gets a corrected page,
                          re-uploads
                                        ▼
                          Reviewer types their name and ticks
                          the authorisation box
                                        ▼
                          Carrier fields filled, signature and date
                          stamped, form fields locked read-only
                                        ▼
                          Executed PDF + audit log entry
```

## What it does not do

These are scope decisions, not gaps.

- **No AI or LLM anywhere in the decision path.** Every check is a
  deterministic rule with a stable id. On a compliance document, a
  hallucinated "looks fine" is worse than no check at all.
- **It never contacts the driver.** It produces a list; a human sends it.
- **It never edits driver-attested content.** Employment history, SSN, date of
  birth, and the driver's signature are the driver's statements. Only
  carrier-side fields are filled.
- **No DocuSign API in version one.** The reviewer downloads the PDF and
  uploads it, which keeps developer accounts, JWT consent, and public
  webhook endpoints off the critical path.

It checks paperwork completeness. It does not replace a compliance review, an
MVR check, a PSP report, or a drug and alcohol query.

## Driver data

Everything runs on one machine. Both processes bind to `127.0.0.1` and no
driver data crosses a network — that is a genuine compliance advantage and
worth stating in any report.

The full Social Security number is never written to the database. It is
validated in memory, then stored as the last four digits plus a salted
SHA-256 hash; the full value exists only inside the PDF on disk. The API
returns `***-**-6789` and nothing else. No log line ever contains a field
value — field keys and rule ids only. A test asserts the number does not
appear in the database file at all.

Storage lives under `backend/storage/`, which is gitignored. Never commit a
real contract PDF. Test fixtures are synthetic and generated at test time
with PyMuPDF.

## Tests

```bash
cd backend && pytest -q          # 217 tests
cd frontend && npm run typecheck && npm run build
```

The rules engine is the product, so it carries the coverage: every `rule_id`
has a case that fires and a case that does not, plus the boundaries that
decide real contracts — a CDL expiring exactly today, a driver turning 21
today, employment gaps of exactly 30 and exactly 31 days.

## Layout

```
backend/     FastAPI, PyMuPDF, pdfplumber, SQLAlchemy, SQLite — see backend/README.md
frontend/    Next.js 15, TypeScript, Tailwind, shadcn/ui     — see frontend/README.md
docs/        The original build prompts
PROJECT_SPEC.md
CLAUDE.md
```

## Departures from the specification

Three gaps in the spec were closed rather than worked around silently. Each
is documented in `backend/README.md` and covered by tests.

1. `cdl.expiry_unreadable` — section 8 gives every date an "unreadable" rule
   except the CDL expiry.
2. `POST /contracts/{id}/void` — the status model has `void` set by a human,
   but no route set it, which also left `DELETE` unreachable.
3. `POST /contracts/{id}/flags/{flag_id}/resolve` — the `flags.resolved`
   column is described as "reviewer may dismiss a warning", with no route to
   do it.
