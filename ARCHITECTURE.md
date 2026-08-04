# Architecture

## Overview

Two deployables: this App (a Docker container, HA Ingress-served SPA,
owns ESPHome connections and the command library) and the [companion
integration](https://github.com/vgyy4/ir-rf-hub-integration) (creates the
actual HA `button`/`switch` entities). The App talks directly to each
ESPHome device's native API via `aioesphomeapi`, using the `ir_rf_proxy`
component -- not through Home Assistant core's own Infrared/Radio
Frequency platforms, since those don't support RF receive at all and only
gained IR receive support recently.

## Half-duplex TX/RX concurrency

`backend/ir_rf_hub/esphome/device_session.py` serializes every TX and RX
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
  see `DOCS.md`.

## Data model

- `EspDevice` -- host/port/credentials (Fernet-encrypted at rest) for one ESPHome device.
- `DeviceEntity` -- one row per `ir_rf_proxy` platform instance discovered via `ListEntities` (domain: infrared/radio_frequency, role: tx/rx). Every "which devices are valid here" filter in the UI queries this table.
- `Command` -- a saved command: name, type, raw timings (alternating mark/space µs), carrier frequency, optional default device. Raw end-to-end, no protocol decoding.

## API surface

REST (`/api/*`) for the SPA, the same handlers under `/api/integration/*`
(bearer-token authed) for the companion integration. `/api/ws` is a
general event fan-out (command/device changes); `/api/ws/recording/{id}`
is the scoped live-capture stream for the recording modal -- one message
per captured signal (a whole mark/space burst arrives atomically from
`ir_rf_proxy`, not byte by byte).

## Pairing

The App generates a single opaque code (base64url JSON: host, port, a
random bearer token) shown once on its Settings page. The integration's
config flow has one field for it -- no separate host/port entry, and the
App stays on Supervisor's isolated Docker network (no `host_network`,
no zeroconf dependency for pairing).
