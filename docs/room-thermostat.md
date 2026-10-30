# Ariston room thermostat on eBUS

How an Ariston room thermostat registers with an Alteas One Net boiler, what it sends, and how the boiler uses it.
Everything below was observed on the bus of this installation with ebusd 26.1 unless marked otherwise.

Frames are written as `QQ ZZ PBSB NN data`: source master, destination (`fe` = broadcast), command, data length,
data. Multi-byte values are little endian; temperatures are signed 16-bit in tenths of a °C.

"Mode 3" and "mode 4" below are thermoregulation modes (`c079`, menu 4.2.1): 3 uses the outdoor sensor only, 4 the
outdoor sensor and the room thermostat. Zone modes (`c679`) are named as such.

## Devices on the bus

| Master | Slave | Device |
|--------|-------|--------|
| `37` | `3c` | Boiler (Alteas One Net 30) |
| `7f` | `84` | Ariston Net Wi-Fi gateway (powered from the bus) |
| `70` | `75` | Room thermostat for zone 1 |
| `00` | – | Appears only while the bus is being enumerated (see below) |
| `31` | `36` | ebusd |

The thermostat used here is a **Cube Room Sensor, wired** (3319116, firmware 1.0.32). The serial it sends on the bus
(`262010629184`) is the serial on its label (`481926010262`) reversed.

## Commands

All of these are broadcasts to `fe`. Values are addressed by a two-byte id; the second byte gives the value's width
(`18`, `26`, `47`, `71`, `96`: 2 bytes; `79`, `91`, `94`: 1 byte).

| Command | Meaning |
|---------|---------|
| `2000` | Value query: one or more ids. Answered with `200f` |
| `200f` | Value answer: records of id, value, flag byte |
| `2001` | Setting query: one id. Answered with `200e` |
| `200e` | Setting answer: id, value, minimum, maximum |
| `2010` | Status broadcast, unsolicited: records of id, value, flag byte |
| `2020` | Write: id, value. The boiler also broadcasts its settings this way, about every 28 minutes |
| `2004` | Error |
| `2031` | Serial number |
| `2034` | Bus reset |
| `2036` | Registration handshake step |
| `203a` | Slave address poll during enumeration |
| `203b` | Slave address cast |

The boiler's `2010` broadcasts carry the zone heat requests (`0191`…`0491`) about every 5 s and the zone status
(`c194`, `6996`) about every 25 s.

## Registration

A thermostat registers by asking for a bus reset. The boiler then enumerates the bus, every device introduces
itself, and the thermostat leads a three-step handshake. Times are relative to the thermostat's first frame.

| t (s) | Frame | Meaning |
|------:|-------|---------|
| 0.0 | `70 fe 2034 00` | Thermostat asks for a bus reset |
| 0.2 | `37 fe 2034 0a 3c 5a ff ff ff ff b3 01 03 00` | Boiler bus reset |
| 0.5 | `70 fe 2031 10 "262010629184" 75 02 00 09` | Thermostat: 12-character serial, slave address, 3 unknown bytes |
| 1.8 | – | Bus signal lost for ~30 ms |
| 2.1 | `37 fe 2034 0a 3c 01 01 11 05 00 b3 01 03 00` | Boiler bus reset, second form |
| 2.4 | `70 fe 2031 …` | Thermostat repeats its serial |
| 3.5 | `00 fe 203a 01 <slave>` | Master `00` polls unused slave addresses `02`…`50` and `fe`, ~123 ms apart, several rounds; nobody answers |
| 10.8 | `70 fe 2036 05 00 b1 00 01 75` | Handshake step 1, led by the thermostat |
| 10.8 | `37 fe 2036 05 00 b1 00 01 3c` | Boiler repeats step 1 with its own slave address, ~50 ms later |
| 13.5 | `7f fe 2034 0a 84 0b 0d 11 50 00 ff 01 03 00` | Gateway bus reset |
| 13.9 | `70 fe 2031 …` | Thermostat repeats its serial |
| 22.4 | `70 fe 2036 05 00 35 01 02 75` | Handshake step 2; boiler (`… 3c`) and gateway (`… 84`) repeat it |
| 29.6 | `70 fe 2036 05 01 00 00 02 75` | Handshake step 3; boiler and gateway repeat it |
| 32 | `70 fe 2000 02 <id>` | Thermostat starts reading zone settings |

The boiler and the gateway also send their own `2031` frames during the sequence (boiler `"342234CZ7097" 3c fe 01 00`,
gateway `"361921HU1271" 84 fe 00 0b`). The `2034` and `2036` payload bytes are not decoded; the values above are the
ones this thermostat used and may depend on the device type or on how many devices are registered.

Polls from ebusd to the boiler time out for about 30 s while the bus is enumerated.

The serial is not checked: a thermostat sending `000000000000` registered and was used exactly like the Cube.

## Normal operation

| Frame | When | Meaning |
|-------|------|---------|
| `37 fe 2000 02 7118` → `70 fe 200f 05 7118 <temp> 00` | When the boiler or gateway asks | Zone 1 room temperature; the thermostat answers within ~80 ms |
| `7f fe 2000 06 7118 7218 7318` → `70 fe 200f 05 7118 <temp> 00` | When the gateway asks for several zones | The thermostat answers only for its own zone |
| `70 fe 2010 05 7118 <temp> 00` | About every minute | Zone 1 room temperature, unsolicited |
| `70 fe 2020 04 6271 <temp>` | When the setpoint is changed on the thermostat | Writes the zone 1 comfort temperature |
| `70 fe 2000 02 c194` | About every 27 s | Reads the zone mode as the boiler reports it (see below) |
| `70 fe 2000 02 c679`, `0120`, `0f23`, `1023` | After registration, then periodically | Reads zone mode, CH enable and two unknown values |
| `70 fe 2001 02 <id>` | After registration | Reads settings with their limits (antifreeze temperature `6426`, comfort temperature `6271`) |
| `70 3c 2000 02 d140`, `70 84 2000 02 cc4b` | Periodically | Reads the boiler's configuration change count and the gateway's connectivity status |
| `70 fe 203b 01 75` | About every 5 minutes | Slave address cast, like the boiler (`3c`) and gateway (`84`) |

The thermostat does not send a zone heat request. The boiler decides the zone heat request itself.

## Zone values

| Id | Value |
|----|-------|
| `6271` | Comfort temperature (22.0 here, range 10–30) |
| `6371` | Reduced temperature (16.0 here) |
| `6426` | Frost protection temperature (5.0 here, range 2–15) |
| `6996` | Zone target temperature, chosen by the boiler from the zone mode |
| `c679` | Zone mode, written by the thermostat |
| `c194` | Zone mode as broadcast by the boiler; follows `c679` |
| `0191` | Zone 1 heat request, decided by the boiler |

Zone modes 0–2 were tested by writing `70 fe 2020 03 c679 <mode>`. The setting answer gives the range 0–3. Which
mode the Cube's MODE key selects (off, manual, programmed) has not been captured from a real Cube; the mapping below
assumes the numbering of the answer.

| Mode | Zone target (`6996`) |
|-----:|----------------------|
| 0 | Frost protection temperature (5.0); heat request off while the room is warmer |
| 1 | Reduced temperature (16.0) |
| 2 | Comfort temperature |
| 3 | Not tested |

The boiler confirms each write with a `200e` answer for `c679` about 2 s later. A holiday set from the gateway also
drops the zone target to the frost protection temperature.

Right after a bus enumeration, a `2000` query for `6996` was answered with 0.0 although the zone target was 22.0; the
`2010` broadcasts carried the right value.

## How the boiler uses the thermostat

**The thermostat setpoint is the zone comfort temperature.** Changing the setpoint on the thermostat writes `6271`
in the boiler. The value stays in the boiler after the thermostat is disconnected and after a power cycle.

**Zone heat request.** With a registered thermostat, the boiler switches the zone heat request (`0191`) on and off by
comparing the thermostat's room temperature with the zone target temperature (`6996`), which is the comfort
temperature in manual mode. This happens in both thermoregulation modes tested, including mode 3 (outdoor sensor only). Without a thermostat the heat request follows the room
thermostat contact TA1, which is bridged in this installation, so it is permanently on.

**Flow temperature.** In the low temperature range, the CH flow setpoint (`6197`, menu 8.3.0) follows

```
flow = slope × (comfort − outdoor) + 20 + offset                                   mode 3, outdoor sensor only
flow = slope × (comfort − outdoor) + slope × influence × (comfort − room) + 20 + offset   mode 4, outdoor + room
```

and is limited to the zone's minimum and maximum CH temperature (20 and 45 °C here). Measured with slope 0.6,
offset +3, room influence (4.2.4) 2:

| Mode | Comfort | Outdoor | Room | Predicted | Boiler |
|------|--------:|--------:|-----:|----------:|-------:|
| 3 | 19.0 | 17.3 | – | 24.0 | 23.4 |
| 3 | 30.0 | 17.3 | – | 30.6 | 30.0 |
| 3 | 21.0 | 18.0 | – | 24.8 | 25.1 |
| 4 | 19.0 | 18.3 | 25.3 | 16.5 → 20.0 (min) | 20.0 |
| 4 | 25.0 | 18.3 | 24.5 | 27.6 | 27.7 |
| 4 | 28.0 | 18.3 | 24.5 | 33.0 | 32.9 |
| 4 | 30.0 | 18.1 | 24.8 | 36.4 | 36.3 |

With influence 2 each degree the room is below the comfort temperature adds 1.2 °C to the flow. Checked again in
mode 4 with comfort 22.0 and outdoor 12.6 (formula's 25.6 °C before the offset and room terms):

| Offset | Influence | Room | Predicted | Boiler |
|-------:|----------:|-----:|----------:|-------:|
| +1 | 2 | 21.7 | 27.0 | 26.9 |
| 0 | 5 | 21.7 | 26.5 | 26.4 |
| 0 | 10 | 20.7 | 33.4 | 33.2 |

The installation manual only calls the room influence (0–20, default 20) proportional and gives no formula; its
curve diagram draws the low temperature curves from 20 °C flow at 20 °C outdoor for a room setting of 20 °C.

## Frost protection

There are two separate frost functions.

**Boiler anti-frost device.** According to the Alteas One Net installation manual it works on the CH flow temperature
sensor only, independently of all other settings: below 8 °C the pump runs for 2 minutes; if the flow is still between
4 and 8 °C it runs for another 2 minutes; below 4 °C the burner fires at minimum power until the flow reaches 33 °C.
It needs correct system pressure, power and gas. It does not look at any room temperature.

**Zone frost protection.** The Cube manuals describe it as: with heating switched off on the thermostat, heating comes
on only when the room falls below 5 °C. On the bus, switching zone 1 off (`fe 2020 03 c679 00`) sets the zone target
temperature (`6996`) to the frost protection temperature (`6426`, 5.0 °C here, range 2–15), and the boiler then
switches the zone heat request (`0191`) on and off from the thermostat's room temperature.

Measured with the zone off and the frost protection temperature at 5.0 °C, by sending the room
temperature from `70` in 0.1 °C steps held for 10 s each, in two identical rounds:

| Room temperature | Heat request |
|------------------|--------------|
| 5.0 °C, falling | stays off |
| 4.9 °C, falling | **on** |
| 5.2 °C, rising | stays on |
| 5.3 °C, rising | **off** |

The heat request comes on as soon as the room is below the frost protection temperature and goes off at that
temperature + 0.3 °C. The boiler reacted 2–6 s after the room temperature frame. With the room at 2, 3 and 4 °C the heat
request stayed on for several minutes; at 6 °C it went off within 3 s.

## Without registration

- A slave address cast for an unknown slave (`fe 203b 01 75`), from any source address, makes the boiler enumerate
  the bus as above, but nothing gets registered.
- `70 fe 2010 05 7118 <temp> 01` from an unregistered source triggers nothing and is not used.
- Switching zone 1 to mode 4 without a registered thermostat raises error 411 within 2 s. Switching back to mode 3
  clears it.

## When the thermostat disappears

Tested in mode 4 with the comfort temperature at 30 °C, by unplugging the thermostat:

1. The boiler does not notice. For 27 minutes it kept calculating the flow from the last room temperature it
   received (flow setpoint 36.2–36.3 °C) and kept the heat request on. It never asked for the room temperature again.
2. The gateway asked for the room temperature (`7f fe 2000 02 7118`, three times in a row) every 3–7 minutes and got
   no answer.
3. After about 27 minutes the gateway started a bus reset (`7f fe 2034 0a 84 01 80 03 38 00 ff 01 03 00`). During the
   enumeration the boiler found the thermostat missing and raised error 411.
4. With 411 active the boiler dropped the room term and fell back to the outdoor curve with the stored comfort
   temperature (flow 30.1 °C). The heat request stayed on.

Switching back to mode 3 clears 411.

## Boiler power cycle

All settings survived ~16 s without power, including values written over eBUS: comfort temperature, thermoregulation
mode, slope and offset. Only the configuration change count (`d140`) restarted from 1. The gateway is powered from
the bus and restarts with the boiler. Both send a start-up form of the bus reset
(`37 fe 2034 0a 3c 01 ff ff 05 00 ff ff ff ff`, `7f fe 2034 0a 84 01 ff ff 30 00 ff ff ff ff`), then their serials
and the handshake.

## Error frames

Errors are broadcast with `2004`: `37 fe 2004 05 <index> <flags> 00 00 3c`. For error 411 (zone 1 room sensor missing)
the index is `69`; flags `03` means active for zone 1, `01` means cleared. Active errors repeat about every 10 s for
two minutes, then about every two minutes.

## Emulating the thermostat

The `ariston_thermostat` Home Assistant integration takes the thermostat's place, reporting a temperature from Home
Assistant through ebusd. It needs ebusd to pass frames both ways without waiting for the bus, so that answers reach
the bus within the boiler's and gateway's patience: a stream of every frame and hex sends from any source address
(`direct -s`, with `--enablehex`). Stock ebusd 26.1 has no such stream; it was run with a patched ebusd that adds it.
Tested on this installation with the Cube unplugged:

- **Registration.** `70 fe 2034 00`, then the serial 0.3 s after each bus reset from the boiler or gateway, as the
  Cube does. The emulator sends no `2036` frames: the boiler and the gateway ran the handshake among themselves and
  the thermostat was registered all the same. Sent right after the reset instead, the serial pre-empted the
  boiler's own frames and the bus kept resetting. A normal registration took about 30 s with five bus resets. After
  it the panel's bus network menu (0.2.0) lists a room sensor for zone 1.
- **Source address.** Answers must come from master `70`. Sent from ebusd's own `31`, the gateway asked for the room
  temperature three times in a row each time.
- **Answers.** 108–139 ms after the question, with no repeat questions.
- **Effect.** Reporting 23.0 °C with a comfort temperature of 22 °C switched the zone heat request off 2.9 s later;
  reporting the real 21.5 °C switched it back on.
- **Address cast.** Without the 5-minute `203b` cast the gateway reset the bus about 30 minutes after every
  registration of the emulator. Sent before registration, the cast makes the boiler enumerate the bus instead.
- **Is it registered?** The address cast doubles as a check. For a slave the boiler knows, it triggers nothing; for one
  it does not know, the boiler starts a bus reset about 1.1 s later. A thermostat that stays silent through a bus
  enumeration is forgotten, so after a restart the emulator casts its address once and registers only if the bus
  resets within 10 s.
- **After registration.** Right after a new registration the boiler held back its zone status broadcasts (`c194`,
  `6996`) until the thermostat had answered a room temperature query. An emulator that waits for those broadcasts
  before answering never gets them; it has to read the comfort temperature with a `2001` query instead.
- **Comfort temperature.** Writing `70 fe 2020 04 6271 <temp>` with 22.5 °C: the boiler answered with `200e` for `6271`
  1 s later, switched the heat request on 5 s later, and the gateway read the new value back.
- **Zone mode.** Writes of `c679` from `70` were accepted, with the effects listed under [Zone values](#zone-values).

### One reported temperature for a house of rooms

Where every room has its own thermostat and valves, the integration can report one temperature computed from all of
them instead of a room's own:

```
reported = zone target − max over heating rooms (room target − room temperature)
```

The boiler compares this with the zone target, so the room furthest below its own target alone decides the heat
request, and in mode 4 the flow rises by slope × influence for each degree that room is short. Rooms that are off do
not count; with every room off the zone target itself is reported, which keeps the heat request off. While the zone
target is the frost protection temperature (zone off, or a holiday), the coldest room's real temperature is reported
instead, so the zone frost protection works on the real rooms.

Reported temperatures are limited to 0–35 °C. When no room temperature is available, the last one is kept for
10 minutes; after that the emulator stops answering and casting, as an unplugged thermostat does, so the boiler falls
back as described under [When the thermostat disappears](#when-the-thermostat-disappears) instead of holding the
flow at a stale value. It answers again as soon as a room temperature is back.

Only zone 1 is supported: the temperature id `7118`, the error 411 flags and the slave address `75` are those of
zone 1. The values for zones 2–6 have not been observed.

## Open questions

- The meaning of the `2034`, `2036` and trailing `2031` bytes, and whether the boiler checks the device type.
- The addresses, temperature ids and error flags of thermostats for zones 2–6 on this boiler.
- What `0f23`, `1023` and `6997` are.
- Whether the boiler ever re-checks a registered thermostat on its own, or only when the gateway resets the bus.
- Whether the room thermostat contact TA1 still matters while a bus thermostat is registered.
- Whether the frost protection hysteresis (+0.3 °C) is fixed or scales with the frost protection temperature.

## Sources

- Ariston Cube Room Sensor installation manual (3319116/3319118) and Alteas One Net installation manual.
