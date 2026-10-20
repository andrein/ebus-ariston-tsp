import "@ebusd/ebus-typespec";
import "./_templates.tsp";

using Ebus;
using Ebus.Num;

namespace Ariston;

// This boiler answers 2000 and 2001 reads of the zone settings with no data. The boiler (master 0x37) broadcasts each
// one as value, min, max (fe 200e) when any master asks with fe 2001 02 <id>, and every panel edit goes out as
// fe 2020 <id> <value>. fe.query.tsp polls those questions; the passive messages here decode the answers and keep
// only the value. The last id byte is the zone (71 = zone 1, 72 = zone 2, ...).
// Zones are handled by the boiler itself, so like the heating circuits of other makers they are a name prefix in the
// boiler circuit rather than a circuit of their own.
namespace Boiler {
  // 4.0.2, used only when thermoregulation is fixed_flow_temperature
  /** Zone 1 fixed flow temperature */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0x65, 0x71)
  model Zone1FixedFlowTemperature {
    @out @divisor(10) @unit("°C") value: SIN;
    @out _: skip4;
  }

  // 4.2.0
  /** Zone 1 temperature range */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0x00, 0x81)
  model Zone1TemperatureRange {
    @out value: temperature_range;
    @out _: skip2;
  }

  // 4.2.1
  /** Zone 1 thermoregulation */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0xc0, 0x79)
  model Zone1Thermoregulation {
    @out value: thermoregulation;
    @out _: skip2;
  }

  /** default *u, the boiler's answer to a query or a panel edit; data after the value is ignored */
  @passive
  @zz(BROADCAST)
  @base(0x20, 0x0e)
  model u {}

  /** default *w, as sent by the front panel */
  @write
  @zz(BROADCAST)
  @base(0x20, 0x20)
  model w {}

  // 4.2.2
  /** Zone 1 slope */
  @inherit(u)
  @ext(0x6a, 0x71)
  model Zone1Slope {
    value: slope;
  }

  // 4.2.3
  /** Zone 1 offset */
  @inherit(u)
  @ext(0x64, 0x71)
  model Zone1Offset {
    value: offset;
  }

  // The writes come in one variant per temperature range, so that the limits ebusd hands to Home Assistant follow
  // the range set on the boiler.
  @condition(Zone1TemperatureRange.value, "0")
  namespace Zone1LowTemperature {
    /** Zone 1 slope */
    @inherit(w)
    @ext(0x6a, 0x71)
    model Zone1Slope {
      value: slope_low;
    }

    /** Zone 1 offset */
    @inherit(w)
    @ext(0x64, 0x71)
    model Zone1Offset {
      value: offset_low;
    }
  }

  @condition(Zone1TemperatureRange.value, "1")
  namespace Zone1HighTemperature {
    /** Zone 1 slope */
    @inherit(w)
    @ext(0x6a, 0x71)
    model Zone1Slope {
      value: slope_high;
    }

    /** Zone 1 offset */
    @inherit(w)
    @ext(0x64, 0x71)
    model Zone1Offset {
      value: offset_high;
    }
  }

  // 4.2.4
  /** Zone 1 room influence */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0xc2, 0x79)
  model Zone1RoomInfluence {
    @out value: UCH;
    @out _: skip2;
  }

  // 4.2.5
  /** Zone 1 maximum CH temperature */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0x60, 0x71)
  model Zone1MaxChTemperature {
    @out @divisor(10) @unit("°C") value: SIN;
    @out _: skip4;
  }

  // 4.2.6
  /** Zone 1 minimum CH temperature */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0x61, 0x71)
  model Zone1MinChTemperature {
    @out @divisor(10) @unit("°C") value: SIN;
    @out _: skip4;
  }

  // 8.3.0. Sent every ~25 s as three records (id, value, flag): 6047, 6197 and 6297. 6047 tracks 6197 but answers
  // its own queries with an unbounded range, and 6297 (58.0 °C) is unidentified, so only 6197 is decoded.
  /** Zone 1 CH flow setpoint */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x10, 0x60, 0x47)
  model Zone1ChFlowSetpoint {
    @out _: skip5;
    @out @divisor(10) @unit("°C") value: SIN;
  }

  // 4.3.4
  /** Zone 1 heat request */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x10, 0x01, 0x91)
  model Zone1HeatRequest {
    @out onoff: onoff;
  }
}
