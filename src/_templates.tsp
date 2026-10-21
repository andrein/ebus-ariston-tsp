import "@ebusd/ebus-typespec";

using Ebus;
using Ebus.Num;
using Ebus.Str;

@values(Values_onoff)
scalar onoff extends BCD;

enum Values_onoff {
  off: 0,
  on: 1,
}

@values(Values_boiler_status)
scalar boiler_status extends UCH;

enum Values_boiler_status {
  standby: 1,
  heating: 2,
  heating_hot_water: 3,
  water_tank: 4,
  circulating: 5,
  manual_test: 23,
  comfort: 24,
  gas_circuit_deaeration: 31,
  auto_calibration: 36,
  low_water_pressure: 51,
  no_flame: 52,
}

@maxLength(1)
scalar skip extends IGN;

@maxLength(2)
scalar skip2 extends IGN;

@maxLength(4)
scalar skip4 extends IGN;

@maxLength(5)
scalar skip5 extends IGN;

@maxLength(12)
scalar serial_number extends STR;

@values(Values_temperature_range)
scalar temperature_range extends UCH;

enum Values_temperature_range {
  low_temperature: 0,
  high_temperature: 1,
}

@values(Values_thermoregulation)
scalar thermoregulation extends UCH;

enum Values_thermoregulation {
  fixed_flow_temperature: 0,
  basic_thermoregulation: 1,
  room_temp_only: 2,
  outdoor_temp_only: 3,
  room_and_outdoor_temp: 4,
}

@values(Values_circulator_type)
scalar circulator_type extends UCH;

enum Values_circulator_type {
  standard_efficiency: 0,
  high_efficiency: 1,
}

@values(Values_boiler_version)
scalar boiler_version extends UCH;

enum Values_boiler_version {
  combi: 0,
}

@values(Values_diverter_valve)
scalar diverter_valve extends UCH;

enum Values_diverter_valve {
  dhw: 0,
  ch: 1,
}

// The write limits follow the zone temperature range (4.2.0): slope 0.2 to 1.0 and offset -7 to +7 for low
// temperature, slope 1.0 to 3.5 and offset -14 to +14 for high temperature. The boiler clamps a written value to the
// limits of the current range (offset +8 became 7, slope 0.1 became 0.2), so a slightly wider limit is safe. Limits on
// an integer-based scalar must be whole numbers, hence 0 and 4 for the slope. ebusd rejects a read value outside the
// limits, so the read uses the unlimited scalar.
@divisor(100)
scalar slope extends UIN;

@minValue(0) @maxValue(1) @step(0.1)
scalar slope_low extends slope;

@minValue(1) @maxValue(4) @step(0.1)
scalar slope_high extends slope;

@divisor(10) @unit("°C")
scalar offset extends SIN;

@minValue(-7) @maxValue(7) @step(1)
scalar offset_low extends offset;

@minValue(-14) @maxValue(14) @step(1)
scalar offset_high extends offset;

// The DHW setpoint range does not depend on any setting (2.0.0: 36 to 60), so the read can share the limits.
@divisor(10) @unit("°C")
@minValue(36) @maxValue(60) @step(1)
scalar dhw_setpoint extends SIN;

// The limits of the zone flow temperatures (set, maximum and minimum CH) follow the zone temperature range: 20 to 45
// in the low range (as the boiler answers), 35 to 82 in the high range (manual).
@divisor(10) @unit("°C")
scalar flow_temperature extends SIN;

@minValue(20) @maxValue(45) @step(1)
scalar flow_temperature_low extends flow_temperature;

@minValue(35) @maxValue(82) @step(1)
scalar flow_temperature_high extends flow_temperature;

// The comfort temperature range does not depend on any setting (the boiler answers 10 to 30), so the read can share
// the limits.
@divisor(10) @unit("°C")
@minValue(10) @maxValue(30) @step(0.5)
scalar comfort_temperature extends SIN;

// Zone mode names as in the Ariston Net API (ZoneMode in github.com/fustom/python-ariston-api).
@values(Values_zone_mode)
scalar zone_mode extends UCH;

enum Values_zone_mode {
  off: 0,
  manual_night: 1,
  manual: 2,
  time_program: 3,
}

@values(Values_comfort_function)
scalar comfort_function extends UCH;

enum Values_comfort_function {
  disabled: 0,
  time_based: 1,
  always_active: 2,
}

// Only 0 and 3 have been seen: cancelled and set from the Ariston Net app.
@values(Values_holiday)
scalar holiday extends UCH;

enum Values_holiday {
  off: 0,
  on: 3,
}
