# Claude Code prompt — frontend

Run this after the backend exists and serves `/api`. Keep `PROJECT_SPEC.md` in
the directory so Claude Code can read the API shapes.

---

## The prompt

Build the frontend for the contract review tool described in `PROJECT_SPEC.md`
in this directory. Read it first — section 6 has the exact API shapes. The
backend already runs at `http://localhost:8000`. Build under `frontend/`.

### Who uses this and what they need

One person, office staff at a trucking company, processing ten to fifteen
driver contracts a week. Each contract is about fifty pages. Their job with
this tool is narrow: see what is wrong, decide whether it matters, approve.

The whole interface should answer one question fast — **which pages does the
driver need to fix?** Everything else is secondary. If someone can upload a
contract and know the answer within ten seconds of the page loading, the design
works.

This is a workhorse tool used every day, not a showcase. Dense, quiet,
information-first. No hero sections, no gradients, no marketing polish.

### Stack

Next.js 15 App Router, TypeScript in strict mode, Tailwind CSS, shadcn/ui,
TanStack Query for server state, react-hook-form with zod on the settings
forms. No global state library — server state plus URL params covers it.

### Screens

**1. Queue** — `/`

Default landing. A table of contracts, newest first: driver name, filename,
status, error count, warning count, upload date, and an action.

Status is the primary scan target, so make it read at a glance without relying
on colour alone — pair each with a label. Filter tabs across the top: All,
Needs review, Clean, Executed. Search box filters by driver name or filename.

Upload lives here as a dropzone that accepts a single PDF. While it processes,
show real progress — extraction takes a few seconds on a fifty-page file, and a
frozen screen reads as broken. On success, go straight to the detail page.

Empty state should tell a first-time user what to do, not just say "no data".

**2. Review detail** — `/contracts/[id]`

The screen that matters. Layout it in this priority order:

*Verdict, at the top.* One line stating the outcome and the pages to fix. If
there are errors: `2 errors · fix pages 18 and 24`. If clean, say so plainly.
This is the answer to their question — nothing should sit above it.

*The driver note, immediately below.* A monospace block of the text from
`GET /contracts/{id}/driver-note`, with a copy button. This gets pasted into a
text message to the driver. Make copying it one click and confirm it worked.

*Flags list.* Errors first, then warnings, visually distinct. Each row: the page
number, the field label, and the message. Clicking a row jumps the preview to
that page. Warnings collapse into an expander since they do not block anything.

*Page preview.* Server-rendered PNG from `/contracts/{id}/preview/{page}`. Page
navigation with previous, next, and a jump-to-page input. Add `?boxes=true` to
show where the signature will land. Do not build a PDF viewer with pdf.js — the
backend renders images, use them.

*Extracted values.* Collapsed by default. A table of every field, its value, and
its page, so the reviewer can spot-check. Mark fields that were never found
distinctly from fields that were found but empty — different problems.

*Approve and execute.* At the bottom, and gated. The button stays disabled
until the reviewer types their name and ticks an explicit authorisation
checkbox reading close to: *I have reviewed this contract and authorise my
signature to be applied.* That tick is the legal basis for the signature stamp,
so do not soften it, do not pre-check it, do not let it be skipped.

If errors are unresolved, allow approval but show a clear warning first that it
will be recorded as an override. Never silently block — the reviewer sometimes
has context the rules do not.

After execution, swap the section for a download button and the approval
record.

**3. Settings** — `/settings`

Three sections.

*Field mapping.* An editable table of field key, label, AcroForm name,
required. Plus a probe tool: upload a sample PDF, get back the widget names and
page text from `POST /config/probe`, so the user can see what their form
actually says and fix mismatches. This screen is where day one is spent — make
it pleasant.

*Signature.* Upload the PNG, preview it. Choose anchor or offset mode. Anchor
takes a search phrase and dx/dy/width/height. Offset takes fractional sliders.
Live preview against a chosen contract via `POST /config/test-placement`, with
the red placement box drawn. Save when it looks right.

*Company details.* Carrier name, representative name, title, MC and DOT numbers.

**4. Audit log** — `/audit`

Read-only table of approvals: contract, approver, timestamp, whether it was
overridden, pages stamped. CSV export button. Nothing here is editable.

### Things I care about

- **Errors from the API must be visible.** A failed upload or a failed execute
  needs a real message the user can act on, not a silent no-op or a raw stack
  trace. A 409 on execute means something specific — say what.
- **Loading states everywhere.** Extraction and stamping take seconds. Skeletons
  on the table, a real progress indication on upload, a disabled button with a
  spinner during execute.
- **Keyboard support on the queue.** Arrow keys to move between rows, Enter to
  open. This person opens fifteen of these a week.
- **Never display a full SSN.** The API returns a masked value; show it masked.
- **Accessible by default.** Real labels on inputs, focus rings, status conveyed
  by text and not colour alone, sensible heading order. shadcn/ui gives most of
  this — do not undo it.
- Put shared API types in `lib/types.ts` mirroring the backend schemas, and all
  fetch calls in a typed client in `lib/api.ts`. No inline `fetch` in components.

### Design direction

Restrained and legible. Pick a real typeface and a small type scale, and use
weight and spacing for hierarchy rather than colour. Reserve colour for meaning
— error, warning, clean — and let everything else be neutral. Generous line
height in the flag messages, since those are read carefully. Tables should be
dense; this is a work tool, not a dashboard.

Support dark mode, since the person using this works night shifts.

### Deliverables

Working `frontend/`, `npm run dev` proxying to the backend, no TypeScript
errors under strict mode, and a short `frontend/README.md`.

Ask me before deviating from the specification. Build the queue and detail
screens first and show me those before starting settings — the detail screen is
where nearly all the value is, and I would rather iterate on it early.
