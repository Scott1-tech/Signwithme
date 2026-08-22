# Opening the desk from somewhere else

By default the contract desk answers only to the computer it runs on. That
is deliberate: the files it handles contain driver Social Security numbers,
and a tool nobody can reach is a tool nobody can breach.

This page is for when that is not enough — you want it on a second desk, or
from home, or on a phone.

---

## First, the one rule

**Create an account before sharing it.** Without one there is no password on
anything, and the whole queue — contracts, SSNs, signed PDFs — is open to
whoever finds the address.

```
cd backend
.venv/bin/python -m app.cli create-user        # Mac
.venv\Scripts\python.exe -m app.cli create-user  # Windows
```

The app enforces this. Start it facing the network with no account and it
refuses, saying why. That is not a warning you can click past.

Once an account exists, everyone signs in — including on the computer
running it.

---

## Option A — Tailscale (recommended)

Tailscale builds a small private network between your own devices. Your
laptop at home can reach the office computer directly, encrypted, without
opening anything to the internet. It is free for personal and small
business use.

**On the office computer**

1. Install from <https://tailscale.com/download> and sign in.
2. Start the desk in shared mode:
   - Windows: `start-shared.bat`
   - Mac: `./start-shared.sh`
3. Note the address it prints, or run `tailscale ip -4`.

**On every other device** — laptop, phone, home computer

1. Install Tailscale and sign in with the same account.
2. Open `http://100.x.y.z:3000`, using the office computer's Tailscale
   address.
3. Sign in with your username and password.

**Why this one.** The address only exists inside your own network. There is
nothing on the public internet to find, scan, or guess. The traffic is
encrypted between devices, and the contracts stay on your computer — no
third party is storing them.

Add it to your phone's home screen and it behaves like an app.

---

## Option B — the office network

Anyone on the same office wifi can reach it, and nobody outside can.

1. Create an account, as above.
2. Start it with `start-shared.bat` / `./start-shared.sh`.
3. The script prints the addresses. On other office machines open
   `http://192.168.x.y:3000`.

Simpler than Tailscale, and enough when everyone who needs it is in the
building. It does not work from home.

If the address changes after a restart, ask whoever manages the router to
give that computer a fixed one.

---

## Option C — a hosted server

Putting this on Render, Fly, or similar makes it reachable from anywhere
with an ordinary link. It is also the only option where driver Social
Security numbers leave your control, so treat it as a business decision
rather than a technical one.

If you go that way, three things are not optional:

- **A paid instance with a persistent disk.** Free tiers wipe their
  filesystem on restart, which would delete executed contracts you are
  required to retain under 49 CFR 391.51.
- **An account, created before the first deploy** — the app refuses
  otherwise.
- **HTTPS**, and `SESSION_COOKIE_SECURE=true` in the environment so the
  session cookie is never sent in the clear.

Check with your insurer and whoever handles your FMCSA compliance first.
"The data never leaves our office" is a genuinely strong position to give
up.

---

## What sharing changes

| | On this machine | Shared |
| --- | --- | --- |
| Address | `localhost:3000` | the computer's network address |
| Login | optional | required |
| Reachable by | you | anyone on that network with an account |
| Encryption | not needed | Tailscale provides it; plain wifi does not |

Two things stay true either way: the app never sends driver data anywhere
itself, and the full Social Security number is never written to the
database.

---

## Managing accounts

```
python -m app.cli create-user            add someone
python -m app.cli list-users             see who has access
python -m app.cli set-password dana      change a password
python -m app.cli disable-user dana      revoke access
```

Changing a password or disabling an account signs that person out
everywhere, immediately.

Approvals record both the typed name and the account that was signed in, so
the audit log shows who authorised each signature and from which login.

---

## A caution about plain HTTP

Shared mode serves plain HTTP, not HTTPS. On Tailscale that is fine — the
tunnel is already encrypted. On office wifi it is acceptable but not ideal.
On a public or shared network it is not: passwords and contracts would
travel readable. Keep this to networks you control.
