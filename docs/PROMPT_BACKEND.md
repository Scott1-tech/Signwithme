# Claude Code prompt — backend

Paste this into Claude Code from an empty `contract-desk/` directory. Keep
`PROJECT_SPEC.md` in that directory so Claude Code can read it.

---

## The prompt

I am building a local-only contract review tool for a US trucking motor
carrier. Read `PROJECT_SPEC.md` in this directory first — it is the source of
truth for scope, data model, API surface, and validation rules. Build the
backend described in section 4.3 under `backend/`.

### What this thing does

Office staff download a signed 50-page driver contract from DocuSign and upload
it here. The backend reads the driver's answers out of the PDF, checks them
against FMCSA and formatting rules, and returns a list of problems with page
numbers. After a human clicks approve, it stamps the carrier signature image
onto the signature pages and writes an audit record.

### Hard constraints

- **Python 3.11+, FastAPI, SQLAlchemy, SQLite.** PyMuPDF for form fields,
  stamping, and page rendering. pdfplumber for word-level text extraction.
- **No AI, no LLM calls, no external API calls anywhere.** Every check is a
  deterministic rule. This is a compliance product.
- **Bind to 127.0.0.1 only.** Driver Social Security numbers are in these files
  and must never cross a network.
- **Never store a full SSN in the database.** Persist `ssn_last4` and a salted
  SHA-256 hash. The full value stays inside the PDF on disk.
- **Never log field values.** Log field keys and rule ids only.
- **Approvals are append-only.** No update or delete route for them, ever.

### Build order

Work in this order and do not move on until each step's tests pass.

**Step 1 — extraction service** (`app/services/extract.py`)

Two paths, exact one first:

- If any page has AcroForm widgets, read `field_name` and `field_value` via
  PyMuPDF.
- Otherwise, or for any field the first path missed, use pdfplumber's
  `extract_words()`. Find the label phrase (may be multiple words, match
  case-insensitively and ignore punctuation), then collect words to its right
  on the same baseline band — vertical tolerance about 4 points, maximum
  horizontal gap configurable per field, default 320 points.

Return an object carrying: values by field key, page number by field key, which
path ran, page count, and a list of field keys that were never found. A field
that could not be located must surface as a flag later, never as silence.

Also expose a `probe(path)` that returns every widget name plus every page's
text. The setup wizard uses it to discover what the labels actually are.

**Step 2 — rules engine** (`app/services/rules.py`)

Implement every rule in specification section 8 with its exact `rule_id`. Each
rule returns a flag carrying `rule_id`, `field_key`, `page`, `severity`, and a
plain-English `message` that gets shown to the user verbatim — write messages
someone can act on, like `CDL expired on 03/01/2025`, not `validation failed`.

Employment history is the fiddly one. Fields are named `emp1_from`, `emp1_to`,
`emp1_company`, `emp2_from` and so on. Parse the spans, sort them, then check:
gaps over 30 days between consecutive jobs, a gap over 30 days between the most
recent job and today, total reach-back under 3 years as an error, and under 10
years as a warning. Treat `Present` and `Current` in an end date as today.

Accept several date formats: `%m/%d/%Y`, `%m-%d-%Y`, `%Y-%m-%d`, `%m/%d/%y`,
`%d %b %Y`, `%B %d, %Y`. An unparseable date is an error, not a silent skip.

Write the tests for this module before the module. Every `rule_id` needs a case
that fires and a case that does not, plus boundaries: a CDL expiring exactly
today, a driver turning 21 today, gaps of exactly 30 and exactly 31 days.

**Step 3 — models and database** (`app/models.py`, `app/database.py`)

Build the four tables in specification section 5. Use UUID primary keys and a
`DATABASE_URL` setting so swapping SQLite for Postgres later is a config change.

**Step 4 — stamping service** (`app/services/stamp.py`)

Resolve signature placements two ways:

- *Anchor*: `page.search_for(phrase)`, then apply dx/dy offsets. Preferred.
- *Offset*: fractions of page width and height, so letter and legal both work.

Anchor mode falls back to offset when the phrase is not found, if configured to.

`apply()` inserts the signature PNG at each placement with
`keep_proportion=True`, draws the date beside it, fills any carrier-side
AcroForm fields from config, sets all widgets read-only, and saves to a new
path. It must never write over the original upload.

Also expose `preview_page(path, page_no, boxes)` returning PNG bytes, drawing
red rectangles where the signature will land.

**Step 5 — API layer** (`app/api/`)

Build every route in specification section 6. Details that matter:

- `POST /contracts` runs extraction and validation synchronously and returns
  the full detail object. Hash the file and reject or link duplicates.
- `POST /contracts/{id}/execute` returns 409 unless an approval exists, and 409
  if already executed. Executing is idempotent-safe: no double stamping.
- `GET /contracts/{id}/driver-note` returns plain text, one line per error, in
  the shape `- page 18: CDL expired on 03/01/2025`. This gets copied into a text
  message to the driver, so keep it clean and free of jargon.
- Approving over unresolved errors is allowed but must set `overridden` true on
  the approval record.

**Step 6 — tests**

pytest. Generate synthetic PDFs at test time with PyMuPDF — one flattened, one
with AcroForm widgets. Never commit a real contract to this repository; they
contain Social Security numbers. Cover everything in specification section 12.

### Deliverables

Working `backend/` per the layout in section 4.3, `requirements.txt` with
pinned versions, `.env.example`, a green pytest run, and a short `backend/README.md`
covering setup and how to run.

Ask me before deviating from the specification. If something in it is wrong or
impossible, say so rather than quietly working around it.
