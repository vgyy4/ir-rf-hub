# IR/RF Hub

Record, name, edit, and fire IR and RF commands through ESPHome devices
running the `ir_rf_proxy` component, and expose them to Home Assistant
automations and dashboards via the companion **IR/RF Hub**
integration.

## Before you start

Each ESPHome device you want to use for recording or firing commands needs
an `ir_rf_proxy` block in its YAML, on top of an existing
`remote_receiver`/`remote_transmitter` configuration. A device can be
receiver-only, transmitter-only, or both, and IR-only, RF-only, or both
(one `ir_rf_proxy` platform entry per direction/domain).

Minimal example, one ESP32 with an IR receiver and an IR transmitter:

```yaml
remote_receiver:
  id: ir_rx
  pin: GPIO32
  dump: none        # ir_rf_proxy streams raw data itself; no need to also dump to logs

remote_transmitter:
  id: ir_tx
  pin: GPIO33
  carrier_duty_percent: 50%   # required 30-50% for IR

ir_rf_proxy:
  - platform: infrared
    remote_receiver_id: ir_rx
  - platform: infrared
    remote_transmitter_id: ir_tx
```

For RF (433MHz etc.), `carrier_duty_percent` must be exactly `100%`, and you
give the proxy a `frequency` (metadata only, not a hardware tune):

```yaml
ir_rf_proxy:
  - platform: radio_frequency
    remote_transmitter_id: rf_tx
    frequency: 433.92MHz
```

### Half-duplex RF front-ends (e.g. CC1101)

If your RF hardware can't receive and transmit at the same time, wire the
transmitter's `on_transmit`/`on_complete` triggers to switch the front-end
into TX mode and back:

```yaml
ir_rf_proxy:
  - platform: radio_frequency
    remote_transmitter_id: rf_tx
    frequency: 433.92MHz
    on_transmit:
      - switch.turn_on: rf_frontend_tx_mode
    on_complete:
      - switch.turn_off: rf_frontend_tx_mode
```

The App always applies a short settle delay before and after every
transmit/receive on a device (configurable per device via the pencil/Edit
icon on that device in the **Devices** screen), so even hardware you
haven't wired an explicit mode switch for gets a safety margin — but
wiring the triggers above is still recommended for anything that
physically can't do both at once.

## Searching for a known remote's command

Instead of recording live or typing raw timings by hand, "Search" (next to
"New Recording") lets you look a command up by name -- pick IR or RF, then
type something like "samsung tv power" or "garage door opener" and pick a
match. It's matched against a bundled offline database (no internet access
needed to search), the raw signal gets rendered from the match, and you can
test-fire it before saving. IR coverage is broad; RF coverage is much
narrower and deliberately excludes rolling-code remotes (garage/gate/car
fobs that change their code every use) -- a stored code for those would be
stale immediately, so there's nothing useful to search for there. See
"Remote code databases" below for sources and how the bundled data stays
current.

## Remote code databases

The search feature above (and the brand/model suggestions offered right
after recording a signal) are backed by three community databases:

- [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) (IR, CC0)
- [IRDB](https://github.com/probonopd/irdb) (IR) -- contains/accesses irdb
  by Simon Peter and contributors, used under permission. For licensing
  details and for information on how to contribute to the database, see
  <https://github.com/probonopd/irdb>.
- [UberGuidoZ/Flipper](https://github.com/UberGuidoZ/Flipper)'s Sub-GHz
  folder (RF, GPL-3.0) -- filtered to the fixed-code protocols the App can
  actually decode/encode (Princeton, CAME) and merged/deduplicated against
  the other sources so the same real-world code found in more than one
  database only shows up once.

The two IR sources are periodically re-fetched and merged in the
background (checked on startup, after an App update, and roughly weekly)
so coverage doesn't just get stale between App releases -- this needs
outbound internet access to GitHub; if it's unavailable the App keeps
using whichever copy it already has (initially, the one bundled in the
image) and just tries again later. (IRDB's own project suggests accessing
its data dynamically per-file over a CDN instead of a periodic bulk
re-fetch, specifically so a product doesn't ship a copy frozen forever at
build time -- the periodic refresh here already avoids exactly that,
just via a single `git clone` instead of roughly 3,200 individual
requests for the same data.) The RF source is not part of this
automatic refresh (it's a few hundred MB even filtered down to just its
relevant folder -- too large to fetch on a schedule on typical Home
Assistant hardware); RF coverage only grows when a new App version ships
with a freshly rebuilt bundle. Either way, the working copy lives outside
this App's backed-up data and is simply rebuilt/re-fetched automatically
if a restore ever leaves it missing -- it's re-derivable public data, not
something a backup needs to carry.

## Backups

Everything the App needs to restore itself -- every recorded command, every
paired ESPHome device (including its encrypted credentials), and the
pairing token -- lives in this App's `/data` volume, which Home Assistant's
own backup system (Settings → System → Backups) already includes whenever
this App is selected, full or partial. No extra setup needed: a "hot"
backup taken while the App is running still gets a consistent snapshot,
since a checkpoint is forced right before Supervisor copies the volume.
The remote code database cache (see above) is deliberately excluded from
the backup itself and rebuilt automatically instead.

**Uninstalling the App removes all of this, on purpose.** Everything
above -- the command database, device credentials, the pairing token, and
the remote-database cache -- lives under this App's `/data` volume with
nothing App-specific stored anywhere else, and Supervisor unconditionally
deletes that entire volume as part of uninstalling an add-on (confirmed
against Supervisor's own source: `App.unload()`, called from
`uninstall()`, removes `path_data` outright -- and that call only happens
on uninstall, never on a plain restart or stop, so routine restarts never
touch this). If you want to keep your commands, back up first.

## Connecting the companion integration

Open this App -- it will show a pairing code on a screen you can't dismiss until you've pasted it into the integration below.
Install the **IR/RF Hub** integration in Home Assistant (via HACS,
or manually), and paste the code into the single field in its setup form.
That's it — no separate host/port entry needed, the code carries everything
required to connect.
