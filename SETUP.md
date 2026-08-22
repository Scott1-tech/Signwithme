# Getting the contract desk running

Written for the person who will actually use this, not for a developer.
You need to do the first part once. After that, starting the app is one
double-click.

---

## Before you start

Two free programs need to be on the computer. Install them, then restart the
computer once.

| | Where to get it | Note |
| --- | --- | --- |
| **Python** | <https://www.python.org/downloads/> | On Windows, tick **“Add Python to PATH”** on the first screen. It is easy to miss and nothing works without it. |
| **Node.js** | <https://nodejs.org> | Take the **LTS** version, the one on the left. |

Then download this project as a folder on the computer that will run it.

---

## Step 1 — Set it up (once)

**Windows:** double-click **`setup.bat`**

**Mac:** open Terminal in the project folder and run `./setup.sh`

It takes about five minutes. It installs what the app needs and creates a
private key used to protect Social Security numbers.

> **Back up `backend\.env`.** That file holds the key. If you lose it, records
> already saved can no longer be matched. Copy it somewhere safe once, now.

---

## Step 2 — Start it

**Windows:** double-click **`start.bat`**

**Mac:** run `./start.sh`

Your browser opens at **http://localhost:3000**. Two small windows appear and
stay open while the app runs — leave them alone.

**To stop:** close those two windows (Windows), or press **Ctrl+C** in the
Terminal (Mac).

Nothing is on the internet. The app only answers to this one computer, which
is why driver Social Security numbers never leave it.

---

## Step 3 — Set it up for your contracts (once)

Three things, in this order.

### 1. Add your signature

Go to **Signatures**. You need the signature as a **PNG image** — a photo of a
signature on white paper, background removed, works fine. Type whose it is,
choose the file, save.

Add one for each person who signs.

### 2. Make a template

Go to **Templates**. Find a contract you have **already signed and finished** —
one that has the signature and date on it — and upload it.

The app reads where the signature and date sit and shows you, drawn on the
page: **red box = signature, blue box = date**.

Check the boxes are in the right places. Untick anything wrong. Save.

> If it finds nothing, that contract probably has not been counter-signed, or
> the signature is text rather than an image. Try a different finished
> contract before assuming it is broken.

### 3. Fill in the company details

Go to **Settings → Company details** and enter the carrier name, the
representative, the MC and DOT numbers.

While you are there, open **Field mapping** and use the probe tool: upload a
blank contract and it shows you exactly how each label is written on your
form. If the wording differs from what is listed, correct it. Otherwise the
app will not find the driver's answers.

---

## Using it day to day

1. Download the completed contract from DocuSign.
2. Open the app. At the top, check the **template**, the **signature**, and
   the **date** — usually already correct.
3. Drop the PDF in.
4. Read the line at the top:
   - **Nothing to fix** → carry on to step 5.
   - **2 errors · fix pages 1 and 4** → copy the note underneath, send it to
     the driver, and upload the corrected contract when it comes back.
5. Type your name, tick the box, press **Approve**.
6. Press **Apply signature**, then download the signed PDF.

It goes to **Completed**, and the approval is recorded in the **Audit log**.

---

## Opening it from another computer or phone

By default the desk answers only to the machine it runs on. To reach it from
elsewhere — another desk, home, a phone — see [`ACCESS.md`](ACCESS.md).

The short version: create an account first, then start it with
`start-shared.bat` / `./start-shared.sh` instead of the usual one. The app
will not face a network without a login, and says so rather than starting
unprotected.

---

## Back it up

Executed contracts must be kept — 49 CFR 391.51 — and one computer is not a
backup. Plug in an external drive and run:

**Windows:** `backup.bat E:\contract-desk-backup`

**Mac:** `./backup.sh /Volumes/BackupDrive/contract-desk`

It copies the contracts, the approval records, and the key. Do it weekly, and
keep the drive encrypted (BitLocker on Windows, FileVault on Mac).

---

## When something goes wrong

**“Python is not installed”** even though you installed it — on Windows this
almost always means the “Add Python to PATH” box was not ticked. Reinstall and
tick it.

**The browser says it cannot connect** — the app takes a few seconds to start.
Wait, then reload. If it still fails, look in the `logs` folder.

**The app says a field is missing on every contract** — the field map does not
match your form. Settings → Field mapping → probe tool.

**Everything is slow the first time** — the first start after setup builds
some things. Later starts are quick.
