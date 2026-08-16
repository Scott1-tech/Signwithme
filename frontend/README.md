# Frontend — Driver Contract Review Desk

Next.js 15 App Router interface for the contract review desk. One person,
office staff at a trucking company, processing ten to fifteen driver
contracts a week.

The whole interface answers one question fast: **which pages does the driver
need to fix?** Everything else is secondary.

## Setup

```bash
cd frontend
npm install
npm run dev
```

Then open <http://localhost:3000>. The backend must be running on
`127.0.0.1:8000` — see `backend/README.md`.

`next.config.ts` rewrites `/api/*` to the backend, so the browser stays on one
origin and there is no CORS preflight. Point it somewhere else with
`BACKEND_URL` if you need to.

```bash
npm run typecheck   # tsc --noEmit, strict mode
npm run lint
npm run build
```

## Screens

| Route | What it is for |
| --- | --- |
| `/` | Queue. Upload, filter, search, open a contract. |
| `/contracts/[id]` | Review detail. The screen that matters. |
| `/settings` | Field map, probe tool, signature placement, company details. |
| `/audit` | Read-only approval log with CSV export. |

### The detail screen, in priority order

1. **Verdict** — one line: `2 errors · fix pages 1 and 2`. Nothing sits above it.
2. **Driver note** — monospace, one click to copy, ready to paste into a text
   message. Only shown when there is something to fix.
3. **Flags** — errors first; warnings collapse into an expander since they do
   not block. Clicking a page number jumps the preview.
4. **Page preview** — server-rendered PNG, with an option to draw the
   signature placement box.
5. **Extracted values** — collapsed. "Not found" and "found but blank" are
   shown differently: the first usually means the field map is wrong, the
   second means the driver skipped it.
6. **Approve and execute** — gated, at the bottom.

The screen opens on the first page that needs fixing rather than page one.

## Things that are deliberate

**The approve gate.** The button stays disabled until a name is typed *and*
the authorisation checkbox is ticked. The checkbox is never pre-checked and
neither can be skipped — it is the legal basis for stamping the signature
under E-SIGN. Do not "streamline" it.

**Approving over errors is allowed.** The reviewer sometimes has context the
rules do not. They get a clear warning that it will be recorded permanently
as an override naming them, and then they may proceed. Never a silent block.

**Errors are never dismissible, warnings are.** Dismissing an error would
erase the distinction between "resolved" and "overridden", and that
distinction is the audit trail.

**Upload shows two phases.** "Uploading 45%" while the bytes transfer, then
"Reading the contract and checking the rules" while the server extracts. The
second phase is the slow one, and a bar stuck at 100% reads as frozen.

**Never a full SSN.** The API returns `***-**-6789` and that is what is shown.
The page preview is an image of the actual contract, so the number is visible
there — that is the document itself, which is what the reviewer is reviewing.

## Design

Restrained and legible. Weight and spacing carry the hierarchy; colour is
reserved for meaning — error, warning, clean — and everything else is
neutral. Tables are dense, figures are tabular so page numbers do not jitter,
and flag messages get generous line height because they are read carefully.

Status never relies on colour alone: every state pairs an icon with a written
label. Dark mode is fully supported, since the person using this works night
shifts.

## Structure

```
app/                     routes
components/ui/           shadcn-style primitives, owned in-repo
components/queue/        queue table, upload dropzone
components/detail/       verdict, driver note, flags, preview, approve
components/settings/     field map, probe, signature, company
lib/types.ts             mirrors backend/app/schemas.py
lib/api.ts               the only place that talks to the backend
```

`lib/types.ts` mirrors the backend Pydantic schemas by hand. Change one,
change the other. There is no inline `fetch` in any component.

### A note on shadcn/ui

The components in `components/ui/` are shadcn/ui components written into the
repo directly rather than pulled with `npx shadcn add`, because
`ui.shadcn.com` is not reachable from this build environment. They are the
same thing shadcn would have written — Radix primitives plus Tailwind classes
and `cva` variants — and they are yours to edit, which is the point of
shadcn/ui. The Radix packages come from npm as normal.

## Known issue

`npm audit` reports three high-severity advisories in `postcss` and `sharp`,
both reached through Next.js 15. Every Next 15 release is affected; the fix
is Next 16, which the specification does not call for. The app binds to
localhost and serves only local files, so none of the three is reachable
here. Worth revisiting if the stack ever moves to Next 16.
