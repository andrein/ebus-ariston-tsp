import "@ebusd/ebus-typespec";
import "./_templates.tsp";

using Ebus;
using Ebus.Num;

namespace Ariston;

// All gateway entries are diagnostics (see boiler.tsp). The Wi-Fi and internet time writes are left out: the emitter
// cannot give a write the same name as its read, and the HA switch sends its command to the read's name.
@zz(0x84)
namespace Gateway {
  // 19.0.0
  /** Wi-Fi */
  @poll(3)
  @id(0x20, 0x00, 0x09, 0x21)
  model Wifi {
    @in _: skip;
    @in onoff: onoff;
  }

  // 19.0.3
  /** Internet time */
  @poll(3)
  @id(0x20, 0x00, 0x14, 0x21)
  model InternetTime {
    @in _: skip;
    @in onoff: onoff;
  }

  // 19.1.0
  /** Connectivity status */
  @poll(3)
  @id(0x20, 0x00, 0xcc, 0x4b)
  model ConnectivityStatus {
    @in _: skip;
    @in @values(Values_connectivity_status) value: UCH;
  }

  // 19.1.1
  /** Signal level */
  @poll(3)
  @id(0x20, 0x00, 0xc3, 0xf0)
  model SignalLevel {
    @in _: skip;
    @in @unit("%") value: UCH;
  }

  // 19.1.2
  /** Active status */
  @poll(3)
  @id(0x20, 0x00, 0xc4, 0xf0)
  model ActiveStatus {
    @in _: skip;
    @in @values(Values_active_status) value: UCH;
  }

  // 19.1.4
  /** Software upgrade status */
  @poll(3)
  @id(0x20, 0x00, 0xc8, 0x9c)
  model SwUpgradeStatus {
    @in _: skip;
    @in @values(Values_sw_upgrade_status) value: UCH;
  }
}

enum Values_connectivity_status {
  off: 0,
  initialization: 1,
  idle: 2,
  access_point_initializing: 3,
  access_point_mode: 4,
  station_connecting: 5,
  station_connected: 6,
  station_provisioning: 7,
  server_connected: 8,
  wifi_error: 9,
}

enum Values_active_status {
  not_provisioned: 0,
  provisioned_not_active: 1,
  active: 2,
}

enum Values_sw_upgrade_status {
  initialization: 0,
  waiting_for_update: 1,
  updating_micro_1: 2,
  updating_micro_2: 3,
}
