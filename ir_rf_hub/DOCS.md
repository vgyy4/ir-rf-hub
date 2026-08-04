# IR/RF Command Hub

Record, name, edit, and fire IR and RF commands through ESPHome devices
running the `ir_rf_proxy` component, and expose them to Home Assistant
automations and dashboards via the companion **IR/RF Command Hub**
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
transmit/receive on a device (configurable per device in **Settings**), so
even hardware you haven't wired an explicit mode switch for gets a safety
margin — but wiring the triggers above is still recommended for anything
that physically can't do both at once.

## Connecting the companion integration

Open this App's **Settings** page and copy the pairing code shown there.
Install the **IR/RF Command Hub** integration in Home Assistant (via HACS,
or manually), and paste the code into the single field in its setup form.
That's it — no separate host/port entry needed, the code carries everything
required to connect.
