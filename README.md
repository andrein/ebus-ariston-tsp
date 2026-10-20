# ebus-ariston-tsp

[TypeSpec](https://typespec.io/) definitions for the **Ariston Alteas One Net** ebusd
configuration. Compiling them with the [`@ebusd/ebus-typespec`](https://github.com/john30/ebus-typespec)
emitter produces [ebusd](https://github.com/john30/ebusd) CSV message definitions.

## Layout

| File | Contents |
|------|----------|
| `src/_templates.tsp` | Shared field types and value lists |
| `src/boiler.tsp` | `Boiler` circuit (slave `0x3c`): live readings, CH/DHW/auto switches, configuration, statistics, maintenance |
| `src/zone.tsp` | Zone 1 messages in the `Boiler` circuit, prefixed `Zone1` (broadcast only): thermoregulation settings (slope and offset write limits follow the temperature range), CH flow setpoint, heat request |
| `src/gateway.tsp` | `Gateway` circuit (Ariston Net, slave `0x84`): Wi-Fi, internet time, connectivity, signal, activation, upgrade status |
| `src/main.tsp` | Imports the circuit files |
| `ha/mqtt-hassio.cfg` | ebusd Home Assistant integration config: stock ebusd 26.1 plus the changes below |

Message comments become the entity names in Home Assistant. A `//` comment above each message names the matching
entry of the technical area menu in the Ariston ONE+ installation and servicing manual.

Live readings are `@poll(1)`; diagnostics are `@poll(3)`. `ha/mqtt-hassio.cfg` differs from the stock file in:

- `filter-name` is disabled: it matches Vaillant naming and would hide most of these messages.
- the poll priority is part of `type_switch-by`, and priority 3 messages get `entity_category: diagnostic`.
- entity names are the message comment instead of the message name.
- the device area is `Technical room`.
- writes are published (`filter-direction = r|u|^w`) and any writable number becomes a `number` entity.

## Build

```sh
npm install
npm run build          # tsp compile src/main.tsp -> out/ariston/*.csv
```

The emitter is a fork, [andrein/ebus-typespec](https://github.com/andrein/ebus-typespec) branch `ariston`, which
has to be checked out and built (`npm ci && npm run build`) in `../ebus-typespec`. It combines two changes to the
released emitter:

- `fix/condition-circuit-zz` ([john30/ebus-typespec#5](https://github.com/john30/ebus-typespec/pull/5)): the condition
  row for a message in the same circuit names that circuit, and has no ZZ for a broadcast message. Without it, ebusd
  resolves the temperature range condition by name in any circuit
  ([john30/ebusd#1811](https://github.com/john30/ebusd/issues/1811)).
- `feat/poll-broadcast-read`: a broadcast model with `@poll` is a polled read, so each `*Query` sits next to the
  setting it refreshes. The released emitter turns every active broadcast model into a write and drops `@poll`.

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
ebusd --checkconfig --configpath=out/ariston                 # loads all 66 messages, 0 errors
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
2. A datapoint read with `20 00` and written with `20 20` has to be two models with distinct names, but the HA
   switch sends its command to the read's name. Writes are therefore left out for now.
3. Value labels use underscores (`heating_hot_water`) since TypeSpec enum members must be identifiers.
4. The emitter writes a header row, `*r`/`*u` default lines and an explicit `level` column; broadcasts emit as `u`.

## References

- Ariston ONE+ installation and servicing manual, technical area (menu numbers and terms):
  <https://library.ariston.co.uk/one-series-installation-amp-service-manual/68650958/43>
- Chaffoteaux Mira C Green config and protocol notes (2000/2001/2010/2020 commands, zone ids, tech menu entries):
  <https://github.com/ysard/ebusd_configuration_chaffoteaux_bridgenet>
- Ariston Clas One config (register ids, error codes): <https://github.com/phateks/EBusD-ClasONE-card>
- Ariston hybrid (energy manager) config: <https://github.com/wrongisthenewright/ebusd-configuration-ariston-bridgenet>
