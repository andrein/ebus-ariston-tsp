import "@ebusd/ebus-typespec";
import "./_templates.tsp";

using Ebus;
using Ebus.Num;

namespace Ariston;

// Comments name the matching technical area entry of the Ariston ONE+ installation and servicing manual.
// @poll(1) marks live readings; @poll(3) marks diagnostics, which the HA integration config files under
// entity_category diagnostic and ebusd polls less often.
@zz(0x3c)
namespace Boiler {
  /** Status */
  @poll(1)
  @id(0x20, 0x00, 0xc0, 0x4b)
  model Status {
    @in _: skip;
    @in value: boiler_status;
  }

  /** Flame */
  @poll(1)
  @id(0x20, 0x00, 0x0e, 0x11)
  model FlameActive {
    @in _: skip;
    @in onoff: onoff;
  }

  // 8.3.1
  /** CH flow temperature */
  @poll(1)
  @id(0x20, 0x00, 0x68, 0x10)
  model ChFlowTemperature {
    @in _: skip;
    @in @divisor(10) @unit("°C") value: SIN;
  }

  // 8.3.2
  /** CH return temperature */
  @poll(1)
  @id(0x20, 0x00, 0x69, 0x10)
  model ChReturnTemperature {
    @in _: skip;
    @in @divisor(10) @unit("°C") value: SIN;
  }

  /** Pressure */
  @poll(1)
  @id(0x20, 0x00, 0x75, 0x47)
  model Pressure {
    @in _: skip;
    @in @divisor(10) @unit("bar") value: UCH;
  }

  // 8.2.8
  /** Gas power */
  @poll(1)
  @id(0x20, 0x00, 0x68, 0x47)
  model GasPower {
    @in _: skip;
    @in @divisor(10) @unit("kW") value: UIN;
  }

  // 8.2.4
  /** Diverter valve */
  @poll(1)
  @id(0x20, 0x00, 0xc0, 0x12)
  model DiverterValve {
    @in _: skip;
    @in value: diverter_valve;
  }

  // 8.2.7
  /** Pump modulation */
  @poll(1)
  @id(0x20, 0x00, 0xc3, 0x00)
  model PumpModulation {
    @in _: skip;
    @in @unit("%") value: UCH;
  }

  // 8.3.5
  /** Outdoor temperature */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0f, 0x76, 0x47)
  model OutdoorTemperature {
    @out @divisor(10) @unit("°C") value: SIN;
  }

  // The switch states are answers to the polled broadcast *Query reads, like the zone settings in zone.tsp; only
  // the value is kept.
  /** CH */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0x01, 0x20)
  model Ch {
    @out onoff: onoff;
    @out _: skip2;
  }

  /** CH query */
  @poll(3)
  @zz(BROADCAST)
  @id(0x20, 0x01, 0x01, 0x20)
  model ChQuery {}

  /** DHW */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0x02, 0x20)
  model Dhw {
    @out onoff: onoff;
    @out _: skip2;
  }

  /** DHW query */
  @poll(3)
  @zz(BROADCAST)
  @id(0x20, 0x01, 0x02, 0x20)
  model DhwQuery {}

  /** Auto function */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x0e, 0x05, 0x20)
  model AutoFunction {
    @out onoff: onoff;
    @out _: skip2;
  }

  /** Auto function query */
  @poll(3)
  @zz(BROADCAST)
  @id(0x20, 0x01, 0x05, 0x20)
  model AutoFunctionQuery {}

  // 2.0.0
  /** DHW setpoint */
  @inherit(u, w)
  @ext(0x61, 0x26)
  model DhwSetpoint {
    value: dhw_setpoint;
  }

  /** DHW setpoint query */
  @poll(3)
  @zz(BROADCAST)
  @id(0x20, 0x01, 0x61, 0x26)
  model DhwSetpointQuery {}

  // 2.1.4
  /** Circulator type */
  @poll(3)
  @id(0x20, 0x00, 0xc2, 0x28)
  model CirculatorType {
    @in _: skip;
    @in value: circulator_type;
  }

  // 2.2.8
  /** Version */
  @poll(3)
  @id(0x20, 0x00, 0xc4, 0x28)
  model BoilerVersion {
    @in _: skip;
    @in value: boiler_version;
  }

  // 2.2.9
  /** Nominal power */
  @poll(3)
  @id(0x20, 0x00, 0x68, 0x29)
  model NominalPower {
    @in _: skip;
    @in @unit("kW") value: UIN;
  }

  // 2.3.7
  /** Pump overrun */
  @poll(3)
  @id(0x20, 0x00, 0xc2, 0x27)
  model PumpOverrun {
    @in _: skip;
    @in @unit("min") value: UCH;
  }

  // 2.4.1
  /** Warning pressure */
  @poll(3)
  @id(0x20, 0x00, 0xc1, 0x2a)
  model WarningPressure {
    @in _: skip;
    @in @divisor(10) @unit("bar") value: UCH;
  }

  // 2.4.5
  /** Pump max PWM */
  @poll(3)
  @id(0x20, 0x00, 0xc9, 0x28)
  model PumpMaxPwm {
    @in _: skip;
    @in @unit("%") value: UCH;
  }

  // 2.4.6
  /** Pump min PWM */
  @poll(3)
  @id(0x20, 0x00, 0xca, 0x28)
  model PumpMinPwm {
    @in _: skip;
    @in @unit("%") value: UCH;
  }

  /** Configuration change count */
  @poll(3)
  @id(0x20, 0x00, 0xd1, 0x40)
  model ConfigChangeCount {
    @in _: skip;
    @in value: UCH;
  }

  // 8.0.0
  /** Diverter valve cycles */
  @poll(3)
  @id(0x20, 0x00, 0x40, 0xd2)
  model DiverterValveCycles {
    @in _: skip;
    @in value: UIN;
  }

  // 8.0.1
  /** Pump run time */
  @poll(3)
  @id(0x20, 0x00, 0x42, 0xd2)
  model PumpRunTime {
    @in _: skip;
    @in @unit("h") value: UIN;
  }

  // 8.0.2
  /** Pump cycles */
  @poll(3)
  @id(0x20, 0x00, 0x44, 0xd2)
  model PumpCycles {
    @in _: skip;
    @in value: UIN;
  }

  // 8.0.3
  /** Lifetime */
  @poll(3)
  @id(0x20, 0x00, 0x50, 0xd9)
  model BoilerLifetime {
    @in _: skip;
    @in @unit("h") value: UIN;
  }

  // 8.0.4
  /** Fan run time */
  @poll(3)
  @id(0x20, 0x00, 0x4a, 0xd2)
  model FanRunTime {
    @in _: skip;
    @in @unit("h") value: UIN;
  }

  // 8.0.5
  /** Fan cycles */
  @poll(3)
  @id(0x20, 0x00, 0x4c, 0xd2)
  model FanCycles {
    @in _: skip;
    @in value: UIN;
  }

  // 8.0.6
  /** CH flame detections */
  @poll(3)
  @id(0x20, 0x00, 0x4e, 0xd2)
  model ChFlameDetections {
    @in _: skip;
    @in value: UIN;
  }

  // 8.0.7
  /** DHW flame detections */
  @poll(3)
  @id(0x20, 0x00, 0x50, 0xd2)
  model DhwFlameDetections {
    @in _: skip;
    @in value: UIN;
  }

  // 8.1.0
  /** CH burner hours */
  @poll(3)
  @id(0x20, 0x00, 0x4b, 0xd1)
  model ChBurnerHours {
    @in _: skip;
    @in @unit("h") value: UIN;
  }

  // 8.1.1
  /** DHW burner hours */
  @poll(3)
  @id(0x20, 0x00, 0x4c, 0xd1)
  model DhwBurnerHours {
    @in _: skip;
    @in @unit("h") value: UIN;
  }

  // 8.1.2
  /** Flame faults */
  @poll(3)
  @id(0x20, 0x00, 0x46, 0xd1)
  model FlameFaults {
    @in _: skip;
    @in value: UIN;
  }

  // 8.1.3
  /** Ignition cycles */
  @poll(3)
  @id(0x20, 0x00, 0x42, 0xd8)
  model IgnitionCycles {
    @in _: skip;
    @in value: UIN;
  }

  // 8.2.2
  /** Fan speed */
  @poll(3)
  @id(0x20, 0x00, 0x40, 0x13)
  model FanSpeed {
    @in _: skip;
    @in @unit("rpm") value: UIN;
  }

  // 8.5.0; 2001 reads answer with the value followed by the allowed min and max.
  /** Months to maintenance */
  @poll(3)
  @id(0x20, 0x01, 0xc6, 0x27)
  model MonthsToMaintenance {
    @in value: UCH;
    @in _: skip2;
  }

  // 8.5.1
  /** Maintenance warning */
  @poll(3)
  @id(0x20, 0x01, 0x0e, 0x20)
  model MaintenanceWarning {
    @in onoff: onoff;
    @in _: skip2;
  }
}
