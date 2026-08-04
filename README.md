# IR/RF Command Hub

> [!WARNING]
> **This project is experimental.** It was built quickly, has not been
> battle-tested across the range of ESPHome/RF hardware out there, and its
> data model, API, and pairing mechanism may change without notice between
> versions. Back up anything important, expect rough edges, and please
> [open an issue](https://github.com/vgyy4/ir-rf-hub/issues) if something
> breaks rather than assuming it's you.

A Home Assistant App for recording, naming, editing, and firing IR and RF
commands through ESPHome devices running the [`ir_rf_proxy`](https://esphome.io/components/ir_rf_proxy/)
component. Pairs with the companion [IR/RF Command Hub integration](https://github.com/vgyy4/ir-rf-hub-integration),
which exposes every recorded command as real Home Assistant `button` and
`switch` entities for automations and dashboards.

## Features

- Animated recording flow: pick IR or RF, pick a receiver-capable ESPHome device, watch the raw signal arrive live, name it, done
- Full-screen raw payload editor -- hand-edit a command's timings directly, save in place or save as a new command
- Per-command default transmitter device, or pick one at fire time
- A per-device half-duplex TX/RX lock, so hardware that can't receive and transmit simultaneously (e.g. CC1101-based RF front-ends) doesn't get corrupted commands -- see `ir_rf_hub/backend/ir_rf_hub/esphome/device_session.py`

## Installing

1. Add this repository to your Home Assistant App store (Settings → Apps → ⋮ → Repositories → add `https://github.com/vgyy4/ir-rf-hub`).
2. Install "IR/RF Command Hub" and start it.
3. Flash `ir_rf_proxy` onto the ESPHome devices you want to use (see `ir_rf_hub/DOCS.md`, or the App's own Documentation tab in Home Assistant) — this needs Home Assistant OS/Supervised, since Apps aren't available otherwise.
4. Install the [companion integration](https://github.com/vgyy4/ir-rf-hub-integration) and pair it using the code shown on the App's Settings page.

## Contributing

Pull requests are welcome for review, but merges into `main` are
restricted to the repository owner while this project is experimental —
see the branch protection settings. Please open an issue to discuss
larger changes before submitting a PR.

## Development

See `ARCHITECTURE.md` for the design (half-duplex concurrency model, data
model, API surface) and `ir_rf_hub/backend/tests/` / `ir_rf_hub/frontend/`
for how to run things locally.
