# Backend — Driver Contract Review Desk

FastAPI service that reads a signed driver contract, checks it against FMCSA
and formatting rules, and — after a human approves — stamps the carrier
signature and writes an audit record.

`PROJECT_SPEC.md` in the repository root is the source of truth. `CLAUDE.md`
lists the constraints that must not be broken.

## Setup

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` and set `SSN_SALT` to a real value before the first real
contract goes through:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Changing the salt later orphans every existing hash, so set it once and keep
it.

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs at <http://127.0.0.1:8000/docs>.

**Bind to `127.0.0.1` only.** Driver Social Security numbers are inside these
files and must not cross a network. There is no authentication because there
is no network exposure; add both together or neither.

## Tests

```bash
pytest -q
```

Every PDF in the suite is generated at test time with PyMuPDF — one
flattened, one with AcroForm widgets. Never commit a real contract: they
contain Social Security numbers.

## How a contract moves through

```
POST /api/contracts   upload, extract, validate — all synchronous
      ↓
  needs_review or clean
      ↓
POST /api/contracts/{id}/approve    human types their name, ticks the box
      ↓
POST /api/contracts/{id}/execute    stamps, flattens widgets read-only
      ↓
GET  /api/contracts/{id}/download
```

Upload runs extraction and validation on the request rather than in a
background job. A fifty-page file takes a few seconds, and the reviewer gets
the answer on the same response.

## Layout

| Path | What it does |
| --- | --- |
| `app/services/extract.py` | AcroForm and label-anchored text extraction |
| `app/services/rules.py` | The validation engine. This is the product. |
| `app/services/stamp.py` | Placement resolution, stamping, page rendering |
| `app/services/config_store.py` | Field map, carrier details, placement — JSON on disk |
| `app/services/audit.py` | Append-only approval writer |
| `app/api/` | Routes, per specification section 6 |
| `app/models.py` | The four tables from specification section 5 |

## Configuration

Two different things get called configuration:

* **Settings** (`app/config.py`) come from the environment: storage root,
  database URL, SSN salt. Set once per machine.
* **App configuration** (`app/services/config_store.py`) is the field map,
  carrier details, and signature placement. The reviewer edits these from the
  settings screen and they live as JSON under `storage/config/`, so they can
  be backed up, diffed, or hand-edited.

### The field map is the day-one job

Canonical field keys (`cdl_expires`, `ssn`, `emp1_from`) are the contract
between the field map and the rules engine. The rules look for
`cdl_expires`; the field map says where `cdl_expires` lives in *this* PDF.
Never rename a canonical key — change its `label` and `anchors` instead.

The shipped anchors are a guess at how a typical owner-operator packet is
worded. Run a real contract through `POST /api/config/probe` to see the
actual widget names and page text, then correct the map. Specification
section 13 lists the questions that answers.

## Deliberate decisions worth knowing

**The full SSN is never persisted.** The database stores `ssn_last4` and a
salted SHA-256 hash. The extracted-fields row holds the masked form
(`***-**-6789`), and the API never returns anything else. The full value
exists only inside the PDF on disk. Validation runs against the real value
before masking, which is why rules run at upload time rather than being
re-derived from stored rows later.

**No message ever echoes an SSN.** The driver note gets pasted into a text
message, so the SSN rules describe the problem — "must be nine digits; 8 were
entered" — without repeating the number.

**Employment fields are optional in the field map.** The employment rules own
that section: `employment.none` already reports history that could not be
read. Marking each `empN_*` field required as well would raise two flags for
one problem.

**Approvals record the placement.** Page numbers and the signature-image hash
are resolved and stored at approval time, so the record states exactly what
was authorised. If the placement config changes afterwards, `execute` returns
409 and asks for a fresh approval rather than stamping something the reviewer
never saw.

## Three departures from the specification

Each one closes a gap rather than changing a decision. All are visible in
code and covered by tests.

1. **`cdl.expiry_unreadable` (new rule id).** Section 8 gives an "unreadable"
   rule to every date on the form except the CDL expiry. An unparseable date
   has to be an error, and reusing `cdl.issue_unreadable` would corrupt the
   counts. The added id is tracked in `rules.ADDED_RULE_IDS` and asserted
   against in the tests, so it stays visible.

2. **`POST /contracts/{id}/void`.** The status model has `void` "set by:
   Human", but section 6 lists no route that sets it — which also left
   `DELETE` unreachable, since a processed contract is `clean` or
   `needs_review` and never sits at `uploaded`.

3. **`POST /contracts/{id}/flags/{flag_id}/resolve`.** The `flags` table has a
   `resolved` column described as "reviewer may dismiss a warning", with no
   route to do it. Only warnings can be dismissed: an error is overridden at
   approval instead, and that distinction is the audit trail.

Two smaller additions: `GET /api/config/signature` returns the stored PNG so
the settings screen can preview it, and `POST /api/config/fields/reset`
restores the default map after a bad edit.

## What this does not do

It checks paperwork completeness. It does not replace a compliance review, an
MVR check, a PSP report, or a drug and alcohol query. It never contacts the
driver, never edits driver-attested content, and uses no AI or LLM anywhere
in the decision path.

## Templates: placement learned from a completed contract

Describing signature coordinates by hand is the slowest part of setting this
up, and it has to be redone whenever a contract is revised. So the app learns
instead: the reviewer uploads one contract that was already signed correctly,
and `services/templates.py` reports what is on it and where.

| Piece | What it does |
| --- | --- |
| `services/templates.py` | Finds signature images and dates, with positions |
| `stamp.apply_marks()` | Stamps at those exact rectangles, scaling if the page size differs |
| `api/templates.py` | Create, review, correct, preview, delete |
| `api/signatures.py` | The signature library |

### Why dates are treated carefully

A driver contract is full of dates that belong to the driver: date of birth,
licence issue and expiry, employment spans. Stamping the carrier's date over
any of those would alter what the driver attested to, which the app must
never do.

So a date only becomes a mark when it sits inside a **signature's own band** —
the vertical strip the signature occupies, reaching a little left and some way
right. That is where a counter-signature date goes, and nothing else on the
page qualifies. `dates_beside_signatures=False` lifts the restriction for a
form where the date is printed somewhere unusual, and the reviewer picks the
right one by hand.

### Detection is reported, never assumed

Marks come back for the reviewer to confirm. Each can be switched off, and
new ones can be placed by hand. A template with nothing enabled cannot be
chosen at upload — it fails at the point of choosing, with an explanation,
rather than silently stamping nothing.

Templates and signatures that have been used on a contract cannot be deleted.
They are part of the record of how that contract came to be signed.
