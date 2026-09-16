# AirTag Timeline

Track AirTag location and battery history from Apple Find My, stored
locally in SQLite and viewable as a self-hosted map.

This started as a fork of
[kennym/find-my-timeline](https://github.com/kennym/find-my-timeline),
whose SQLite + Flask + Leaflet design this project reuses. Its auth/poll
layer is different: upstream uses `pyicloud`, which only supports Apple's
"Devices" API (iPhone/iPad/Mac/Watch/AirPods) and cannot see AirTags at
all. This project uses [`findmy`](https://github.com/malmeloo/FindMy.py)
instead, which implements the actual AirTag report-fetch-and-decrypt
protocol.

## How it works

AirTags don't report their location to your account directly — nearby
iPhones relay encrypted "sightings" to Apple, and only the AirTag's owner
can decrypt them, using a private key that lives on the Mac(s) where the
AirTag was set up. This tool:

1. Exports that private key, once, from this Mac's local Find My cache.
2. Logs into your Apple ID (the same account the AirTag is paired to).
3. Periodically asks Apple for encrypted sightings and decrypts them
   locally with the exported key.
4. Stores the decoded location + battery level in SQLite.
5. Serves a local map (Leaflet + OpenStreetMap tiles) over the history.

## Setup

```bash
git clone <this repo>
cd find-my-timeline
python3 -m venv .venv
.venv/bin/pip install -e .

# One-time: export your AirTags' private keys from this Mac
.venv/bin/find-my-timeline import-keys

# Log into the Apple ID your AirTags are paired to (prompts for 2FA)
.venv/bin/find-my-timeline auth

# Poll in the background and open the map
.venv/bin/find-my-timeline start
```

By default the map opens at `http://127.0.0.1:5000`.

## Commands

| Command | Description |
|---|---|
| `find-my-timeline import-keys` | One-time: export AirTag keys from this Mac |
| `find-my-timeline auth` | Log into Apple ID (2FA supported) |
| `find-my-timeline poll` | Run the polling loop only |
| `find-my-timeline web [--open/--no-open]` | Serve the map only |
| `find-my-timeline start` | Poll + serve the map together |
| `find-my-timeline devices` | List tracked AirTags |
| `find-my-timeline stats` | Show database statistics |

## Configuration

Environment variables (or a `.env` file in the working directory):

| Variable | Default | Description |
|---|---|---|
| `ICLOUD_USERNAME` | — | Apple ID email, used by `auth` if not passed as `--username` |
| `ICLOUD_PASSWORD` | — | Apple ID password; prompting interactively is recommended instead |
| `POLL_MIN_INTERVAL` | `7` | Minimum minutes between polls |
| `POLL_MAX_INTERVAL` | `10` | Maximum minutes between polls |
| `DATABASE_PATH` | `~/.find-my-timeline/locations.db` | SQLite database path |
| `WEB_HOST` | `127.0.0.1` | Web server bind address |
| `WEB_PORT` | `5000` | Web server port |

## Data locations

| Path | Contents |
|---|---|
| `~/.find-my-timeline/keys/*.json` | Exported AirTag private keys (`0600`) |
| `~/.find-my-timeline/account.json` | Apple session (`0600`) |
| `~/.find-my-timeline/locations.db` | Location + battery history |

## Security

- `keys/*.json` and `account.json` are sensitive. Anyone holding a key
  file can decrypt that AirTag's location history; `account.json` is an
  authenticated Apple session. Back them up like passwords, not like
  regular app data.
- The web UI has no authentication of its own. It binds to `127.0.0.1`
  by default — keep it that way unless you put a reverse proxy with
  auth in front of it.
- Location history is sensitive personal data. Protect `locations.db`
  accordingly.

## License

MIT — see `LICENSE`. Original SQLite/Flask/Leaflet design and copyright
from [kennym/find-my-timeline](https://github.com/kennym/find-my-timeline).
