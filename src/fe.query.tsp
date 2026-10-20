import "@ebusd/ebus-typespec";

using Ebus;

namespace Ariston;

// Broadcast questions (fe 2001 02 <id>) that make the boiler broadcast a setting as value, min, max, which the
// passive messages in boiler.tsp and zone.tsp decode. A read to the broadcast address cannot be declared with
// @zz(BROADCAST): the emitter turns any active broadcast into a write and drops @poll. Without @zz the models are
// emitted as polled reads, and ebusd takes the fe destination and the circuit from this file's name, which only works
// for an id of up to 5 characters.
namespace Queries {
  /** Boiler CH query */
  @poll(3)
  @id(0x20, 0x01, 0x01, 0x20)
  model BoilerCh {}

  /** Boiler DHW query */
  @poll(3)
  @id(0x20, 0x01, 0x02, 0x20)
  model BoilerDhw {}

  /** Boiler auto function query */
  @poll(3)
  @id(0x20, 0x01, 0x05, 0x20)
  model BoilerAutoFunction {}

  /** Boiler DHW setpoint query */
  @poll(3)
  @id(0x20, 0x01, 0x61, 0x26)
  model BoilerDhwSetpoint {}

  /** Zone 1 fixed flow temperature query */
  @poll(3)
  @id(0x20, 0x01, 0x65, 0x71)
  model Zone1FixedFlowTemperature {}

  /** Zone 1 temperature range query */
  @poll(3)
  @id(0x20, 0x01, 0x00, 0x81)
  model Zone1TemperatureRange {}

  /** Zone 1 thermoregulation query */
  @poll(3)
  @id(0x20, 0x01, 0xc0, 0x79)
  model Zone1Thermoregulation {}

  /** Zone 1 slope query */
  @poll(3)
  @id(0x20, 0x01, 0x6a, 0x71)
  model Zone1Slope {}

  /** Zone 1 offset query */
  @poll(3)
  @id(0x20, 0x01, 0x64, 0x71)
  model Zone1Offset {}

  /** Zone 1 room influence query */
  @poll(3)
  @id(0x20, 0x01, 0xc2, 0x79)
  model Zone1RoomInfluence {}

  /** Zone 1 maximum CH temperature query */
  @poll(3)
  @id(0x20, 0x01, 0x60, 0x71)
  model Zone1MaxChTemperature {}

  /** Zone 1 minimum CH temperature query */
  @poll(3)
  @id(0x20, 0x01, 0x61, 0x71)
  model Zone1MinChTemperature {}
}
