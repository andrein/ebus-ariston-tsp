import "@ebusd/ebus-typespec";
import "./_templates.tsp";

using Ebus;
using Ebus.Num;
using Ebus.Dtm;

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

  // 4.8.0 to 4.8.2 on the boiler panel, which reads them from the gateway. 2001 reads answer with the value followed
  // by the allowed min and max.
  /** Pilot enable */
  @poll(3)
  @id(0x20, 0x01, 0x0b, 0x81)
  model PilotEnable {
    @in onoff: onoff;
    @in _: skip2;
  }

  /** Learning quality */
  @poll(3)
  @id(0x20, 0x01, 0x69, 0xc0)
  model LearningQuality {
    @in value: SIN;
    @in _: skip4;
  }

  /** Periodicity */
  @poll(3)
  @id(0x20, 0x01, 0x61, 0xc0)
  model Periodicity {
    @in value: SIN;
    @in _: skip4;
  }

  // Broadcast by the gateway when holiday mode is set or cancelled in the Ariston Net app or portal; the boiler then
  // drops the zone target temperature to the frost protection temperature. The end time (mm hh, 23:59 when set from the app)
  // is skipped.
  /** Holiday */
  @passive
  @zz(BROADCAST)
  @id(0x20, 0x71)
  model Holiday {
    @out onoff: holiday;
    @out _: skip2;

    /** end */
    @out date: HDA3;
  }

  // Broadcast each time the gateway fetches the weather from the internet (about every 80-90 min), as two records
  // (id, value, flag): 7617 the outdoor temperature and c19a, whose top bit is set from sunset to sunrise. The lower
  // bits of c19a change with the weather condition; their meaning is not confirmed, so they are left out.
  /** Internet weather */
  @passive
  @qq(0x7f)
  @zz(BROADCAST)
  @id(0x20, 0x10, 0x76, 0x17)
  model InternetWeather {
    /** outdoor temperature */
    @out @divisor(10) @unit("°C") temperature: SIN;

    @out _: skip3;

    /** day or night */
    @out daylight: day_night;
  }

  // Broadcast only while the bus is enumerated (see the boiler's serial number).
  /** Serial number */
  @passive
  @qq(0x7f)
  @zz(BROADCAST)
  @id(0x20, 0x31)
  model SerialNumber {
    @out value: serial_number;
    @out _: skip4;
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
