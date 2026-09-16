# AirTag Timeline CLI — Design

Status: approved 2026-09-15.

## Origin

Requested: fork [kennym/find-my-timeline](https://github.com/kennym/find-my-timeline)
into a minimal, self-hostable CLI that records AirTag location + battery
history and serves it as a local HTML map.

Finding during research: `find-my-timeline` uses `pyicloud`, which only
implements Apple's Find My *Devices* API (iPhone/iPad/Mac/Watch/AirPods).
AirTags are Find My *network accessories*, a separate encrypted-report
protocol pyicloud has no code for. The upstream repo cannot track AirTags
under any configuration. Confirmed by grepping pyicloud's source (zero
AirTag/accessory references) and by inspecting this Mac's local Find My
state (`OwnedBeacons/` holds 22 accessory private-key records, separate
from `Devices.data`).

Resolution: keep `find-my-timeline`'s SQLite + Flask + Leaflet UI (well
suited to the goal, reusable close to as-is), replace its auth/poll layer
with the [`findmy`](https://github.com/malmeloo/FindMy.py) library, which
implements the actual AirTag report-fetch-and-decrypt protocol.

## Architecture

Same three-piece shape as upstream: CLI (Click) → SQLite → Flask + Leaflet
map. Only the auth/poll layer is new.

```
src/find_my_timeline/
  cli.py         # click commands
  auth.py        # AppleAccount login + session persistence (findmy-based)
  keys.py        # OwnedBeacons .record -> portable JSON key export
  poller.py      # interval loop, fetch_location() -> DB
  database.py    # sqlite schema + queries
  web.py         # flask app + JSON API
  templates/
    index.html   # leaflet map + timeline sidebar (packaged, not top-level)
```

Packaging templates inside the package (not at repo root, as upstream has
it) is required, not cosmetic: Flask's `template_folder="../../templates"`
trick only resolves correctly against an editable checkout. A real `pip
install` of upstream's package ships without its HTML file.

## Components

**`keys.py` / `import-keys` command** — one-time. Reads every `.record`
file in `~/Library/Group Containers/group.com.apple.icloud.searchpartyuseragent/Library/Storage/OwnedBeacons/`
via `findmy.FindMyAccessory.from_plist(...)` and writes one JSON key file
per accessory to `~/.find-my-timeline/keys/<name-or-uuid>.json`. Must run
on a Mac where the AirTags were set up — it's the only place the private
keys exist. The JSON files themselves are portable to any machine
afterward. These files are key material: treat them like passwords.

**`auth.py`** — `findmy.AppleAccount` + `findmy.LocalAnisetteProvider`
(built-in, no external anisette server). Same interactive UX as upstream:
email + password, then 2FA (SMS or trusted device). Session persisted to
`~/.find-my-timeline/account.json`.

**`poller.py`** — same random-interval loop as upstream (7–10 min
jitter, signal-based graceful shutdown). `poll_once()` loads the key
JSONs, calls `account.fetch_location(accessories)`, and for each
`LocationReport` records `latitude`, `longitude`, `horizontal_accuracy`,
`confidence` (1–3), and `battery_status` — decoded from the report's
status byte via the 2-bit lookup FindMy.py's own example uses
(`0b00 Full / 0b01 Medium / 0b10 Low / 0b11 Very Low`).

**`database.py`** — same schema as upstream with two column swaps:
`battery_level REAL` → `battery_status TEXT`, `position_type TEXT` →
`confidence INTEGER`. Everything else (upsert_device, record_location,
indexes, query filters) unchanged.

**`web.py` / `index.html`** — unchanged except the JS battery formatter
(percentage → 4-level icon/text) and dropping the dead `static_folder`
param. `web`/`start` gain `--open/--no-open` (default open) to launch a
browser tab, per the original request to "open a self-hosted page."

## CLI surface

| Command | Purpose |
|---|---|
| `import-keys` | One-time: OwnedBeacons → `~/.find-my-timeline/keys/*.json` |
| `auth` | Apple ID login (email + password + 2FA), saves session |
| `poll` | Run the polling loop only |
| `web [--open]` | Serve the map UI |
| `start` | Poll + web together |
| `devices` | List tracked accessories |
| `stats` | Database summary |

## Data flow

```
OwnedBeacons/*.record --(import-keys, once)--> ~/.find-my-timeline/keys/*.json
Apple ID login --(auth)--> ~/.find-my-timeline/account.json
[poll loop, every 7-10 min]
  keys.json + account.json -> account.fetch_location() -> LocationReport
  -> decode -> sqlite locations table
[web]
  sqlite -> /api/devices, /api/locations, /api/stats -> Leaflet map + timeline panel
```

## Dropped from upstream

Dockerfile, docker-compose.yml, `.dockerignore`, GH Actions docker
workflow, Unraid XML template, `ca_profile.xml`, icon/preview images, the
unused `schedule` dependency (never imported — upstream's poller already
hand-rolls its interval loop), the `pyicloud` dependency.

## Setup (end state, what the README documents)

```
pip install -e .
find-my-timeline import-keys   # once, on this Mac
find-my-timeline auth          # Apple ID + 2FA
find-my-timeline start         # polls in background, opens map at :5000
```

## Error handling

- `import-keys` finds zero `.record` files → clear message, exit 0 (not
  an error — just nothing to import yet).
- A fetch fails (rate limit, transient network, expired session) →
  logged, loop continues to the next interval — same pattern as
  upstream's existing `try/except` around `get_devices()`.
- Session on disk has expired → same remediation message pattern as
  upstream ("re-run auth").

## Testing

Upstream ships no tests. Adding one lightweight `unittest` module
covering: SQLite round-trip (insert a location, read it back) and the
battery-status byte decode (the one piece of genuinely non-trivial logic
in this design — a bit-shift table lookup that's easy to get subtly
wrong). No framework, no fixtures — matches the size of what's being
verified.

## Security notes

- `~/.find-my-timeline/keys/*.json` and `account.json` are sensitive:
  the keys let anyone holding them decrypt that AirTag's location
  history; the account session is an authenticated Apple session token.
  Both are written with `0600` permissions (owner read/write only, no
  group/world access).
- Location data is personal and sensitive by nature; this is unchanged
  from upstream's own security notice, just carried forward.
