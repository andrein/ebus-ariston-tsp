# ebus-ariston-tsp

[TypeSpec](https://typespec.io/) definitions for the **Ariston Alteas One Net** ebusd
configuration. Compiling them with the [`@ebusd/ebus-typespec`](https://github.com/john30/ebus-typespec)
emitter produces [ebusd](https://github.com/john30/ebusd) CSV message definitions.

## Layout

| File | Contents |
|------|----------|
| `src/_templates.tsp` | Shared field types and value lists |
| `src/boiler.tsp` | `Boiler` circuit (slave `0x3c`): live readings, status (also from its periodic broadcast), CH/DHW switches, thermoregulation (the AUTO button), DHW setpoint and comfort mode, configuration, statistics, maintenance, serial number |
| `src/zone.tsp` | Zone 1 messages in the `Boiler` circuit, prefixed `Zone1` (broadcast only): thermoregulation mode and curve (slope and offset write limits follow the temperature range), comfort, reduced, target and set temperatures, mode, CH flow setpoint, heat request |
| `src/gateway.tsp` | `Gateway` circuit (Ariston Net, slave `0x84`): Wi-Fi, internet time, connectivity, signal, activation, upgrade status, pilot settings, holiday, serial number |
| `src/main.tsp` | Imports the circuit files |
| `ha/mqtt-hassio.cfg` | ebusd Home Assistant integration config: stock ebusd 26.1 plus the changes below |

Message comments become the entity names in Home Assistant. A `//` comment above each message names the matching
entry of the technical area menu in the Ariston ONE+ installation and servicing manual.

Live readings are `@poll(1)`; diagnostics are `@poll(3)`. `ha/mqtt-hassio.cfg` differs from the stock file in:

- `filter-name` is disabled: it matches Vaillant naming and would hide most of these messages.
- the poll priority is part of `type_switch-by`, and priority 3 messages get `entity_category: diagnostic`.
- entity names are the message comment instead of the message name, plus the field comment when there is one.
- the device area is `Technical room`.
- writes are published (`filter-direction = r|u|^w`): a writable number becomes a `number`, an on/off a `switch`, and a
  value list a `select` entity. ebusd then leaves out the read-only entity of the same message, except while the write
  is conditional and its condition is not resolved yet; the zone 1 settings with range-dependent write limits
  therefore get no sensor at all (`type_switch-u-number`).
- zone 1 settings other than the offset and set temperature, the DHW reduced and frost protection temperatures, pump
  modulation, diverter valve and the ebusd global entities are `entity_category: diagnostic`, matched by message name.
- string fields are published only for the serial numbers.
- an optional `type_icon` column in the type switch lists sets an entity icon (thermoregulation, CH, DHW).
- scan results (`scan.<address>` circuits) are not published.
- the adapter firmware update check sits on the ebusd device instead of a device of its own.

## Build

```sh
npm install
npm run build          # tsp compile src/main.tsp -> out/ariston/*.csv
```

The emitter is a fork, [andrein/ebus-typespec](https://github.com/andrein/ebus-typespec) branch `ariston`, which
has to be checked out and built (`npm ci && npm run build`) in `../ebus-typespec`. It combines three changes to the
released emitter:

- `fix/condition-circuit-zz` ([john30/ebus-typespec#5](https://github.com/john30/ebus-typespec/pull/5)): the condition
  row for a message in the same circuit names that circuit, and has no ZZ for a broadcast message. Without it, ebusd
  resolves the temperature range condition by name in any circuit
  ([john30/ebusd#1811](https://github.com/john30/ebusd/issues/1811)).
- `feat/poll-broadcast-read` ([john30/ebus-typespec#6](https://github.com/john30/ebus-typespec/pull/6)): a broadcast model with `@poll` is a polled read, so each `*Query` sits next to the
  setting it refreshes. The released emitter turns every active broadcast model into a write and drops `@poll`.
- `fix/nested-namespace-conditions` ([john30/ebus-typespec#7](https://github.com/john30/ebus-typespec/pull/7)): a model
  gets its own conditions plus those of every enclosing namespace. The released emitter only uses the innermost ones,
  so a write in two nested conditional namespaces would lose the outer condition.

It is a `file:` dependency because the package ships no built `dist` and a git dependency would install it unbuilt.

## Mapping (ebusd CSV → TypeSpec)

An ebusd row is `type,circuit,name,comment,QQ,ZZ,PBSB,ID, [field]*`, where a field is
`name,part,type,divisor/values,unit,comment`.

- `r` / `w` / `b` → read model (default) / `@write` / `@passive`
- circuit → enclosing `namespace`; `ZZ` → `@zz(0xNN)` at namespace level; `ZZ=fe` → `@zz(BROADCAST)`
- `PBSB`+`ID` → `@id(0xPB,0xSB, …id bytes)` — e.g. `2000`+`6810` → `@id(0x20,0x00,0x68,0x10)`
- field direction: read value/skip = `@in` (inbound from slave); write value = `@out`; broadcast value = `@out` (master-sent)
- data type → an `Ebus.Num` / `Str` / `Dtm` scalar (`UCH`, `SIN`, `UIN`, `BCD`, …); `IGN:1` → the `skip` template
- `divisor` → `@divisor(n)`; `unit` → `@unit("…")`; inline `k=label;…` → `enum Values_* {…}` + `@values(...)`
- `[cond=v]` row prefix → `@condition(Model.field, "v")` on the model or an enclosing namespace; `@minValue` /
  `@maxValue` / `@step` → the `range` column (`withMinMax`)

## Verification

The generated CSV is validated with ebusd's own parser:

```sh
ebusd --checkconfig --configpath=out/ariston                 # loads all 95 messages, 0 errors
ebusd --checkconfig --dumpconfig=csv --configpath=out/ariston # normalized message dump
```

Decoding is checked against frames captured from the boiler, without a bus:

```sh
ebusd -f --readonly --scanconfig=none -d /dev/null --configpath=out/ariston --inject=stop \
  37fe200e086a713c0014006400/ 37fe20100f604706010061970601006297440200/
# Zone1 Slope: 0.60;0.20;1.00   Zone1 ChFlowSetpoint: 26.2
```

## Deployment

The Home Assistant eBUSd add-on reads the generated CSV from `/config/ebusd-ariston-tsp` (`--configpath`) and the
integration config from `/config/mqtt-hassio.cfg` (`--mqttint`), with `--mqtttopic=Ariston`. After `npm run build`, copy
`out/ariston/*.csv` there and restart the add-on.

## Emitter naming notes

1. Message and circuit names are PascalCased (`ChFlowTemperature`, `Boiler`); MQTT topics and unique ids follow them.
2. A setting answered with `20 0e` and written with `20 20` shares one name through `@inherit(u, w)` bases, so HA gets
   one entity that reads and writes it. A datapoint read directly with `20 00` cannot share its name with a write, and
   the HA entity sends its command to the read's name, so the gateway's writes are left out for now.
3. Value labels use underscores (`heating_hot_water`) since TypeSpec enum members must be identifiers.
4. The emitter writes a header row, `*r`/`*u` default lines and an explicit `level` column; broadcasts emit as `u`.

## References

- Ariston ONE+ installation and servicing manual, technical area (menu numbers and terms):
  <https://library.ariston.co.uk/one-series-installation-amp-service-manual/68650958/43>
- Chaffoteaux Mira C Green config and protocol notes (2000/2001/2010/2020 commands, zone ids, tech menu entries):
  <https://github.com/ysard/ebusd_configuration_chaffoteaux_bridgenet>
- Ariston Clas One config (register ids, error codes): <https://github.com/phateks/EBusD-ClasONE-card>
- Ariston hybrid (energy manager) config: <https://github.com/wrongisthenewright/ebusd-configuration-ariston-bridgenet>
