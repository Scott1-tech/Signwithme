# Driver Contract Review Desk — Project Specification

Version 1.0 · Grand One LLC · Prepared August 2026

---

## 1. Main purpose of the app

**In one sentence:** the app reads a signed driver contract, checks it against
FMCSA and formatting rules, tells the reviewer exactly which pages are wrong,
and stamps the carrier signature once a human approves.

### The problem today

Grand One LLC onboards ten to fifteen drivers per week. Each driver receives a
contract package of roughly fifty pages through DocuSign. Today the process is:

1. A staff member prepares the contract by hand.
2. The driver signs it in DocuSign.
3. A staff member opens the returned PDF and reads all fifty pages, looking for
   blank fields, bad dates, expired licences, and employment gaps.
4. A company representative signs every signature page by hand.
5. The file is stored for the driver qualification file.

Steps 3 and 4 are the expensive ones. At fifteen drivers a week, manual review
is several hours of skilled attention spent looking for blanks — and it is the
step most likely to miss something an FMCSA auditor will later find.

### What the app changes

| Step | Before | After |
| --- | --- | --- |
| Read the driver's answers | Human, page by page | Automatic, seconds |
| Check for errors | Human, easy to miss | Deterministic rules, never tired |
| Identify what to fix | Human writes notes | Page-numbered list, copy-paste ready |
| Fill carrier fields | Human types | Automatic from config |
| Sign carrier side | Human signs each page | One approve click, then stamped |
| Audit record | Ad hoc | Timestamped log per approval |

### What the app deliberately does NOT do

These are scope decisions, not missing features. They exist because of legal
constraints and because they keep version one shippable.

- **It never contacts the driver.** The app produces a list of problems. The
  human sends that list however they want — text, phone, a photo of one page.
  This avoids resending fifty pages for a single blank box.
- **It never edits what the driver attested to.** Employment history, SSN, date
  of birth, and the driver's signature are the driver's statements. Altering
  them after signing would invalidate the document. The app fills only
  carrier-side fields.
- **It uses no AI or LLM anywhere in the decision path.** Every check is a rule
  with a defined outcome. This is a compliance product; a hallucinated "looks
  fine" is worse than no check at all.
- **It does not integrate with the DocuSign API in version one.** The reviewer
  downloads the completed PDF and uploads it. This removes developer accounts,
  JWT consent, webhooks, and public endpoints from the critical path. API
  integration is phase two.

### Success criteria

Version one is successful when:

- A reviewer can process a signed contract in under two minutes.
- Zero false "clean" results across twenty real contracts — the app must never
  say a contract is fine when a required field is blank.
- Every executed contract has an audit entry naming the approver.
- No driver personal data leaves the reviewer's machine.

---

## 2. Users and roles

| Role | Who | What they do |
| --- | --- | --- |
| Reviewer | Office staff / owner | Uploads contracts, reads flags, approves, downloads |
| Administrator | Owner | Configures field mappings, rules, signature placement |
| Auditor | FMCSA / insurance | Reads the audit log and executed files, read-only |

Version one may treat reviewer and administrator as the same person with no
login. Add authentication when more than one person uses it.

---

## 3. End-to-end flow

```
DocuSign (driver signs)
   │
   │  reviewer downloads the completed PDF
   ▼
Upload  ──►  Extract  ──►  Validate  ──►  Review queue
                                              │
                              ┌───────────────┴───────────────┐
                              │                               │
                         clean / warnings              errors present
                              │                               │
                              │                     reviewer contacts driver
                              │                     out of band, gets a
                              │                     corrected page, re-uploads
                              │                               │
                              └───────────────┬───────────────┘
                                              ▼
                                    Reviewer clicks approve
                                              │
                                              ▼
                                  Auto-fill carrier fields
                                  Stamp signature + date
                                  Flatten form fields
                                              │
                                              ▼
                              Executed PDF + audit log entry
```

### Contract status model

| Status | Meaning | Set by |
| --- | --- | --- |
| `uploaded` | File received, not yet processed | System |
| `extracted` | Driver values read successfully | System |
| `needs_review` | One or more errors found | Validator |
| `clean` | No errors; warnings may exist | Validator |
| `approved` | Reviewer authorised the signature | Human |
| `executed` | Signed, stamped, and stored | System |
| `superseded` | Replaced by a corrected upload | Human |
| `void` | Abandoned | Human |

`executed` is terminal. A contract is never edited after it reaches it; a
correction produces a new record linked by `supersedes_id`.

---

## 4. Architecture

### 4.1 Version one — single machine

```
┌─────────────────────────────────────────────┐
│  Reviewer's laptop                          │
│                                             │
│  ┌───────────────┐      ┌────────────────┐  │
│  │  Next.js UI   │◄────►│  FastAPI       │  │
│  │  localhost    │ HTTP │  localhost     │  │
│  └───────────────┘      └───────┬────────┘  │
│                                 │           │
│                  ┌──────────────┼────────┐  │
│                  ▼              ▼        ▼  │
│              SQLite        File store   Log │
└─────────────────────────────────────────────┘
```

Everything runs locally. Driver SSNs never touch a network. This is a genuine
compliance advantage and worth stating in any report.

### 4.2 Stack

**Backend — Python 3.11+**

| Concern | Choice | Why |
| --- | --- | --- |
| Web framework | FastAPI | Async, auto OpenAPI docs, typed with Pydantic |
| PDF form fields | PyMuPDF | Reads widgets, stamps images, renders previews |
| PDF text | pdfplumber | Word-level coordinates for label-anchored extraction |
| Database | SQLAlchemy + SQLite | Zero setup; swap to Postgres by changing one URL |
| Validation | Pydantic v2 | Request and response schemas |
| Tests | pytest | Rules must be tested; they are the product |

Python is not negotiable for the backend. The PDF toolchain has no equivalent
in Node.

**Frontend — TypeScript**

| Concern | Choice | Why |
| --- | --- | --- |
| Framework | Next.js 15, App Router | Familiar, good defaults |
| Language | TypeScript, strict mode | Catches shape errors against the API |
| Styling | Tailwind CSS | Fast, no CSS files to maintain |
| Components | shadcn/ui | Accessible primitives, owned in-repo |
| Data fetching | TanStack Query | Cache, retry, invalidation |
| Forms | react-hook-form + zod | Config editing screens |
| PDF preview | Backend-rendered PNG | Avoids pdf.js worker complexity |

### 4.3 Repository layout

```
contract-desk/
├── backend/
│   ├── app/
│   │   ├── main.py                FastAPI app, CORS, router mounting
│   │   ├── config.py              Settings from environment
│   │   ├── database.py            Engine, session, Base
│   │   ├── models.py              SQLAlchemy tables
│   │   ├── schemas.py             Pydantic request/response
│   │   ├── api/
│   │   │   ├── contracts.py       Upload, list, detail, approve, execute
│   │   │   ├── config_routes.py   Field map, carrier, signature
│   │   │   └── audit.py           Audit log read + export
│   │   └── services/
│   │       ├── extract.py         AcroForm + text extraction
│   │       ├── rules.py           Validation engine
│   │       ├── stamp.py           Carrier fill + signature
│   │       └── audit.py           Append-only log writer
│   ├── tests/
│   │   ├── conftest.py            Synthetic PDF fixtures
│   │   ├── test_extract.py
│   │   ├── test_rules.py
│   │   └── test_stamp.py
│   ├── storage/                   gitignored
│   │   ├── uploads/
│   │   ├── executed/
│   │   └── signatures/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx               Queue
│   │   ├── contracts/[id]/page.tsx  Review detail
│   │   └── settings/page.tsx      Field map + signature setup
│   ├── components/
│   ├── lib/api.ts                 Typed API client
│   ├── lib/types.ts               Mirrors backend schemas
│   └── package.json
├── CLAUDE.md
└── README.md
```

---

## 5. Data model

### `contracts`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `original_filename` | text | As uploaded |
| `stored_path` | text | Relative to storage root |
| `executed_path` | text nullable | Set on execution |
| `file_hash` | text | SHA-256, detects duplicate uploads |
| `page_count` | int | |
| `driver_name` | text nullable | Convenience for the queue |
| `status` | text | See status model |
| `extraction_source` | text | `acroform`, `text`, or `acroform+text` |
| `contract_type` | text | e.g. `owner_operator_plan_a` |
| `supersedes_id` | uuid nullable | Links a correction to what it replaced |
| `created_at` / `updated_at` | timestamp | |

### `extracted_fields`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `contract_id` | uuid FK | |
| `field_key` | text | e.g. `cdl_expires` |
| `label` | text | Human name shown in the UI |
| `value` | text nullable | |
| `page` | int nullable | 1-based |
| `found` | bool | False if the extractor could not locate it |

**SSN handling.** Store `ssn_last4` and a salted hash. Never persist the full
number in the database. The full value lives only inside the PDF on disk.

### `flags`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `contract_id` | uuid FK | |
| `field_key` | text | |
| `page` | int nullable | Drives "which page to send the driver" |
| `severity` | text | `error` or `warning` |
| `rule_id` | text | e.g. `cdl.expired`, stable for reporting |
| `message` | text | Plain English, shown verbatim |
| `resolved` | bool | Reviewer may dismiss a warning |

### `approvals`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `contract_id` | uuid FK | |
| `approved_by` | text | Typed name of the representative |
| `approved_at` | timestamp | Server time |
| `error_count_at_approval` | int | |
| `overridden` | bool | True if approved with errors outstanding |
| `pages_stamped` | json | List of page numbers |
| `signature_hash` | text | SHA-256 of the signature image used |
| `ip_address` | text | |

`approvals` is append-only. No update or delete endpoint exists for it.

---

## 6. API surface

Base URL `http://localhost:8000/api`. All responses JSON unless noted.

### Contracts

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/contracts` | Upload a PDF (multipart). Extracts and validates synchronously. Returns the full detail object. |
| `GET` | `/contracts` | Queue. Filters: `status`, `q`, `page`, `page_size`. |
| `GET` | `/contracts/{id}` | Full detail: fields, flags, summary, placements. |
| `GET` | `/contracts/{id}/preview/{page}` | PNG render of a page. Query `?boxes=true` draws signature placement rectangles. |
| `GET` | `/contracts/{id}/driver-note` | Plain-text, copy-paste list of what to fix. |
| `POST` | `/contracts/{id}/approve` | Body: `approved_by`, `acknowledge_errors`. Creates an approval record. |
| `POST` | `/contracts/{id}/execute` | Stamps and writes the executed PDF. Requires a prior approval. 409 if already executed. |
| `GET` | `/contracts/{id}/download` | Executed PDF. |
| `POST` | `/contracts/{id}/supersede` | Body: new upload. Links records. |
| `DELETE` | `/contracts/{id}` | Only when status is `uploaded` or `void`. |

### Configuration

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` `PUT` | `/config/fields` | The field map. Keyed by `contract_type`. |
| `GET` `PUT` | `/config/carrier` | Company values and signature placement. |
| `POST` | `/config/signature` | Upload the signature PNG. |
| `POST` | `/config/probe` | Upload a PDF, get back widget names and page text. Powers the setup wizard. |
| `POST` | `/config/test-placement` | Given placement settings and a contract id, return a preview PNG without saving. |

### Audit

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/audit` | Paginated approvals, newest first. |
| `GET` | `/audit/export` | CSV download for an auditor. |

### Key response shape

```json
{
  "id": "…",
  "original_filename": "smith_owner_operator.pdf",
  "status": "needs_review",
  "page_count": 52,
  "driver_name": "John Smith",
  "extraction_source": "text",
  "summary": {
    "error_count": 2,
    "warning_count": 1,
    "pages_to_fix": [18, 24]
  },
  "fields": [
    { "field_key": "cdl_expires", "label": "Expiration Date",
      "value": "03/01/2025", "page": 18, "found": true }
  ],
  "flags": [
    { "rule_id": "cdl.expired", "field_key": "cdl_expires", "page": 18,
      "severity": "error", "message": "CDL expired on 03/01/2025",
      "resolved": false }
  ],
  "placements": [
    { "page": 52, "x": 60.0, "y": 254.0, "width": 150.0,
      "height": 32.0, "how": "anchor" }
  ],
  "can_execute": false
}
```

---

## 7. Extraction strategy

Completed DocuSign envelopes are usually **flattened** — the form fields are
burned into the page and no longer readable as fields. The app handles both
cases and always tries the exact one first.

**Path A — AcroForm.** If any page has widgets, read `field_name` and
`field_value` directly. Exact, no ambiguity.

**Path B — label-anchored text.** Extract words with coordinates, find the
label phrase on a line, then collect words to its right within a vertical
tolerance and a maximum horizontal gap. Configurable per field.

**Merge.** If path A ran but some fields were not found, path B fills the gaps.
`extraction_source` records which ran.

**Never found is an error, not a silence.** Any required field the extractor
cannot locate produces an error flag. Failing loudly matters more than a clean
looking result.

---

## 8. Validation rules

Rules live in one module, each with a stable `rule_id` so reporting can count
"how often does the CDL expire on us". Severity is `error` (blocks execution
unless overridden) or `warning` (informational).

| rule_id | Severity | Check |
| --- | --- | --- |
| `field.missing` | error | Required field not found in the PDF |
| `field.blank` | error | Required field found but empty |
| `ssn.length` | error | Not exactly nine digits |
| `ssn.invalid` | error | Area 000/666/900+, group 00, or serial 0000 |
| `cdl.state_invalid` | error | Not a US state or DC code |
| `cdl.number_format` | error | Unexpected characters |
| `cdl.issue_unreadable` | error | Date cannot be parsed |
| `cdl.issue_future` | error | Issue date after today |
| `cdl.expired` | error | Expiry on or before today |
| `cdl.expiring_soon` | warning | Expiry within 60 days |
| `cdl.expiry_before_issue` | error | Ordering impossible |
| `dob.unreadable` | error | Date cannot be parsed |
| `dob.under_21` | error | Under 21 — cannot drive interstate, 391.11 |
| `dob.implausible` | warning | Age over 90 |
| `phone.length` | error | Not 10 or 11 digits |
| `email.format` | error | Fails a basic address pattern |
| `signature.driver_missing` | error | Driver signature block empty |
| `signature.date_unreadable` | error | Signature date cannot be parsed |
| `signature.date_future` | error | Signed in the future |
| `employment.none` | error | No history readable at all |
| `employment.company_missing` | error | Dates present, company name blank |
| `employment.date_unreadable` | error | From or to cannot be parsed |
| `employment.reversed` | error | End before start |
| `employment.gap` | error | Over 30 days between consecutive jobs |
| `employment.recent_gap` | error | Over 30 days between last job and today |
| `employment.under_3_years` | error | History reaches back under 3 years, 391.21 |
| `employment.under_10_years` | warning | Under 10 years of CDL employment history |

### Regulatory basis

- **49 CFR 391.11** — a driver must be at least 21 to operate in interstate
  commerce.
- **49 CFR 391.21** — the application must show three years of employment, and
  ten years of employment where a CDL was held.
- **49 CFR 391.51** — the driver qualification file must be retained; this is
  why superseded documents are kept rather than deleted.

This app checks paperwork completeness. It does not replace a compliance
review, an MVR check, a PSP report, or a drug and alcohol query.

---

## 9. Signature stamping

### Placement

**Anchor mode (preferred).** Search each page for a phrase such as "Carrier
Representative", then offset from the first hit. Survives page shifts between
contract versions.

**Offset mode (fallback).** Fixed position expressed as a fraction of page
width and height, so letter and legal pages both work.

Placement settings are saved per `contract_type`. Configure once, then every
contract of that type stamps automatically.

### Legal safeguards

Auto-stamping is valid under the E-SIGN Act when the signer genuinely intends
to sign. The app builds that intent into the flow:

1. The reviewer must tick an explicit authorisation checkbox.
2. The reviewer must type their name.
3. An immutable approval record captures who, when, from where, the hash of the
   signature image used, and whether errors were outstanding.
4. Approving over unresolved errors is allowed but recorded as `overridden`.

**Do not remove the approve step to make the app faster.** It is the entire
legal basis for the stamp.

### After stamping

Form fields are set read-only so the executed file cannot be altered by
reopening it. The original upload is retained alongside the executed version.

---

## 10. Security and data handling

| Concern | Approach |
| --- | --- |
| Network exposure | Bind to `127.0.0.1` only. Never `0.0.0.0` in version one. |
| SSN at rest | Store last four plus a salted hash. Never the full number in the DB. |
| PDF storage | Local disk, outside the repo, gitignored. Full-disk encryption on the laptop. |
| Logs | Never log field values. Log field keys and rule ids only. |
| Backups | Encrypted external drive. Driver qualification files must be retained per 391.51. |
| Deletion | Only `uploaded` or `void` records may be deleted. Executed contracts are never deleted. |
| Auth | Not required for single-user local. Add before any network deployment. |

---

## 11. Build plan

### Version one, three days

| Day | Goal | Done when |
| --- | --- | --- |
| 1 | Field mapping against a real contract | The detail view shows correct values for every field on a real signed PDF |
| 2 | Rules tuned, signature placement configured | The preview red box sits correctly and the flag list matches a manual read |
| 3 | Ten real contracts processed, notes written | Executed PDFs open correctly and the audit log has ten entries |

If time runs short, the honest scope cut is: keep upload, extract, validate,
and the driver note. Drop stamping and do the signature in DocuSign by hand.
The review time saved is where most of the value sits anyway.

### Phase two

- DocuSign Connect webhook, so completed envelopes arrive automatically
- Multiple contract types with separate field maps and rule sets
- Bulk approval for clean contracts
- Driver qualification file completeness dashboard
- Multi-user login with per-reviewer audit attribution

### Phase three

- Expiry monitoring across the fleet, alerting before a CDL or medical card lapses
- Export to the existing driver management system
- Scanned document OCR for paper applications

---

## 12. Testing requirements

The rules engine is the product. It must be tested.

**Fixtures.** Generate synthetic PDFs at test time with PyMuPDF — one
flattened, one with AcroForm fields. Never commit a real driver contract to the
repository; it contains a Social Security number.

**Required test cases.**

- Extraction: flattened, fillable, and mixed. Multi-word labels. A label present
  with no value to its right. A field genuinely absent.
- Every rule id: at least one case that fires and one that does not.
- Boundaries: CDL expiring exactly today, driver turning 21 today, an employment
  gap of exactly 30 and exactly 31 days.
- Stamping: anchor found, anchor absent with offset fallback, multi-page,
  fields read-only afterwards.
- API: execute before approve returns 409, double execute returns 409, upload of
  a non-PDF returns 400.

Target: complete coverage of `rules.py` before anything else.

---

## 13. Open questions to resolve on day one

1. Are the returned PDFs flattened or do they retain form fields? Run the probe
   endpoint against a real file to find out.
2. Exactly how is each label written on the form? "CDL Number" versus "Driver's
   License Number" decides whether extraction works.
3. How is employment history laid out — numbered blocks or a table? A table
   layout needs a different extraction approach.
4. Is the carrier signature phrase identical on every page?
5. How many contract types are in use, and do they share a field map?
