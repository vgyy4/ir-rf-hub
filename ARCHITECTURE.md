# Architecture

## Overview

Two deployables: this App (a Docker container, HA Ingress-served SPA,
owns ESPHome connections and the command library) and the [companion
integration](https://github.com/vgyy4/ir-rf-hub-integration) (creates the
actual HA `button`/`switch`/`select`/`remote` entities). The App talks
directly to each
ESPHome device's native API via `aioesphomeapi`, using the `ir_rf_proxy`
component -- not through Home Assistant core's own Infrared/Radio
Frequency platforms, since those don't support RF receive at all and only
gained IR receive support recently.

## Half-duplex TX/RX concurrency

`ir_rf_hub/backend/ir_rf_hub/esphome/device_session.py` serializes every TX and RX
operation against one device through a single `asyncio.Lock`:

- A recording session holds the lock for its entire duration. Since
  `asyncio.Lock` is FIFO-fair, a `transmit()` call that arrives mid-recording
  simply queues on `acquire()` -- no hand-rolled queue needed.
- A second `start_recording()` while one is active is rejected immediately
  (checked before attempting the lock), rather than queued -- an
  open-ended interactive wait is bad UX for a second person.
- Settle timers (`tx_settle_ms` / `rx_stop_settle_ms`, per-device, default
  150ms) run *before* the lock is released, giving half-duplex RF
  front-ends (e.g. CC1101) time to switch modes. Wire your device's
  `on_transmit`/`on_complete` triggers to actually flip the front-end --
  see `ir_rf_hub/DOCS.md`.

## Data model

- `EspDevice` -- host/port/credentials (Fernet-encrypted at rest) for one ESPHome device, plus per-device `tx_settle_ms`/`rx_stop_settle_ms`/`connect_timeout_s`.
- `DeviceEntity` -- one row per `ir_rf_proxy` platform instance discovered via `ListEntities` (domain: infrared/radio_frequency, role: tx/rx). Every "which devices are valid here" filter in the UI queries this table.
- `Command` -- a saved command: name, type, carrier frequency, optional default device, and either a single `raw_timings` payload, or (for a detected/chosen two-shape signal) a `raw_timings` leader plus separate `repeat_timings`/`repeat_protocol` fired `repeat_count - 1` more times after it. `esphome/signal_shapes.py` clusters a recording session's captures and detects common NEC-family leader/repeat framing automatically; the recording wizard falls back to a manual disambiguation step when a capture is ambiguous. Still raw timings end-to-end either way -- no full protocol *decoding* (button codes, addresses, etc.), just leader/repeat framing.

## API surface

REST (`/api/*`) for the SPA, the same handlers under `/api/integration/*`
(bearer-token authed) for the companion integration. `/api/ws` is a
general event fan-out (command/device changes); `/api/ws/recording/{id}`
is the scoped live-capture stream for the recording modal -- one message
per captured signal (a whole mark/space burst arrives atomically from
`ir_rf_proxy`, not byte by byte).

Device management is a full subsystem, not just CRUD: `/api/devices/discover`
merges local mDNS discovery with devices the companion integration has
separately reported seeing (`esphome/integration_discovery.py`), and
`/api/devices/host-network` reads Supervisor's own gateway/subnet so the
SPA can offer a copy-paste static-IP YAML snippet after adding a device.

## Remote code database (search + recording-time suggestions)

`esphome/protocol_decode.py` (IR: NEC/NECext, Sony SIRC) and
`esphome/rf_protocol_decode.py` (RF: Princeton, CAME) do structural
protocol decode/encode -- timings to (protocol, address/key, command/bit
count) and back -- verified against the canonical IRP protocol
definitions (IR) and Flipper's own firmware source (RF) rather than
guessed, since a wrong bit-timing convention would silently produce a
non-functional signal.

`esphome/remote_database_build.py` fetches, parses, and merges several
public per-device code databases into one index keyed by that same
(protocol, address/key, command/bits) tuple -- see its own docstring for
sources/licensing/why-only-these-protocols. `esphome/remote_database.py`
is the read side: `lookup_bundled[_rf]()` (signal → suggested name,
used right after recording) and `search_bundled()` (text → ranked
candidates, used by the Search modal) both read the same index, so a
search result already carries everything `encode_nec`/`encode_princeton`/
`encode_came` need to render a real, fireable, save-ready signal with no
extra round trip.

Two copies of the index can exist: a bundled one shipped in the image
(built by `scripts/build_remote_database.py`, committed), and a runtime
one in `/data/remote_db_cache/` that `esphome/remote_database_updater.py`
keeps current in the background (checked on startup, after an App version
bump, and roughly weekly -- see that module's docstring for exactly what
"checked" vs "refetched" means). `remote_database.py` prefers the runtime
copy when present, falling back to the bundled one. Only the two IR
sources are part of that runtime refresh; the RF source is bundled-only
(too large to refetch on a schedule -- see remote_database_build.py). The
runtime cache is deliberately excluded from HA backups (`rootfs/backup_pre
.sh`/`backup_post.sh` move it out of `/data` for the snapshot window) since
it's re-derivable public data, not something worth carrying in a backup.

## Pairing

Primary path is automatic: the App POSTs to Supervisor's Discovery API
(`http://supervisor/discovery`, `supervisor_discovery.py`) every 60s with
`{service: "ir_rf_hub", config: {host, port, token}}` until paired, which
Home Assistant Core turns into a one-click "Discovered" card for the
companion integration -- no code to copy in the common case. This is why
the App does not use `host_network`: staying on Supervisor's isolated
Docker network is what makes the internal `host`/`port` in that discovery
payload meaningful, and it also means pairing needs no zeroconf/mDNS
dependency on the App's side.

The manual fallback (App running outside Supervisor, or the integration
installed after the App gave up re-announcing) still exists: the App
generates a single opaque code (base64url JSON: host, port, a random
bearer token). There's no Settings page -- the first time the App is
opened and it isn't yet paired, `GET /api/pairing-status` returns
`{paired: false, code}` and the SPA shows a non-dismissable full-screen
gate with that code (leading with "check for a Discovered card first",
the code as the fallback), polling the same endpoint until the
integration's first successful `/api/integration/*` call flips a
persistent `paired` flag (`api/rest/integration.py`), at which point the
gate closes and never reappears (a later restart or brief disconnect
doesn't re-lock the user out). Either path, the integration's config flow
ends up with the same three values (host, port, token) -- no separate
host/port entry for the user in the manual case either.
