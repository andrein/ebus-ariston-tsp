from conftest import protocol
from protocol_frames import (
    BOILER_QUERY,
    BOILER_RESET,
    BOILER_SETTINGS_CAST,
    BOILER_STATUS_CAST,
    COMFORT_ANSWER,
    ENUMERATION_ZONES_ANSWER,
    GATEWAY_QUERY,
    GATEWAY_RESET,
    GATEWAY_ZONES_ANSWER,
)

Frame = protocol.Frame
StreamLine = protocol.StreamLine


def test_temperature_is_signed_tenths_little_endian():
    assert protocol.encode_temperature(21.8).hex() == "da00"
    assert protocol.encode_temperature(-0.5).hex() == "fbff"


def test_serial_as_the_cube_sends_it():
    assert protocol.serial("262010629184", 0x75) == "fe203110" + b"262010629184".hex() + "75020009"


def test_room_temperature_answer_and_cast():
    assert protocol.room_temperature_answer(22.0) == "fe200f057118dc0000"
    assert protocol.room_temperature_cast(22.0) == "fe2010057118dc0000"


def test_bus_reset_request():
    assert protocol.bus_reset_request() == "fe203400"


def test_recognises_error_411_active_but_not_cleared():
    assert protocol.is_room_sensor_missing(Frame.parse("37fe200405690300003c"))
    assert not protocol.is_room_sensor_missing(Frame.parse("37fe200405690100003c"))


def test_recognises_resets_and_queries_from_boiler_and_gateway():
    assert protocol.is_bus_reset(Frame.parse(BOILER_RESET))
    assert protocol.is_bus_reset(Frame.parse(GATEWAY_RESET))
    assert protocol.is_room_temperature_query(Frame.parse(BOILER_QUERY))
    assert protocol.is_room_temperature_query(Frame.parse(GATEWAY_QUERY))


def test_ignores_own_reset_request_and_other_queries():
    assert not protocol.is_bus_reset(Frame.parse("31fe203400"))
    assert not protocol.is_room_temperature_query(Frame.parse("37fe200002c194"))


def test_stream_lines():
    line = StreamLine.parse("1793091239.008 r " + BOILER_QUERY)
    assert line.kind == "r" and line.timestamp == 1793091239.008 and line.frame.data.hex() == "7118"
    failed = StreamLine.parse("1793091240.100 e 31fe200f057118dc0000 ERR: arbitration lost")
    assert failed.kind == "e" and failed.error == "ERR: arbitration lost"
    slave = StreamLine.parse("1793091241.000 r 313c2000025917 0400112233")
    assert slave.frame.destination == 0x3C


def test_other_lines_are_not_stream_lines():
    assert StreamLine.parse("direct mode started") is None
    assert StreamLine.parse("zz:ERR: invalid argument") is None
    assert StreamLine.parse("1793091239.008 r 37fe20000371") is None


def test_gateway_query_for_several_zones_includes_ours():
    assert protocol.is_room_temperature_query(Frame.parse("7ffe200006711872187318"))
    assert not protocol.is_room_temperature_query(Frame.parse("7ffe20000472187318"))
    assert not protocol.is_room_temperature_query(Frame.parse("37fe200003c97118"))


def test_master_address_of_the_zone_1_sensor():
    assert protocol.master_of(0x75) == 0x70


def values(frame):
    return protocol.boiler_values(Frame.parse(frame))


def test_values_from_the_boiler_status_cast():
    assert values(BOILER_STATUS_CAST) == {
        bytes.fromhex("c194"): (b"\x02",),
        bytes.fromhex("6996"): (bytes.fromhex("dc00"),),
        bytes.fromhex("c294"): (b"\x02",),
    }


def test_values_from_the_boiler_settings_cast_and_answers():
    assert values(BOILER_SETTINGS_CAST)[protocol.ZONE_MODE_ID] == (b"\x02",)
    assert values(BOILER_SETTINGS_CAST)[protocol.COMFORT_ID] == (bytes.fromhex("dc00"),)
    assert values(COMFORT_ANSWER)[protocol.COMFORT_ID] == tuple(bytes.fromhex(v) for v in ("dc00", "6400", "2c01"))


def test_answers_give_all_values_but_the_zone_target():
    assert values(GATEWAY_ZONES_ANSWER) == {bytes.fromhex("0591"): (b"\x00",), bytes.fromhex("0691"): (b"\x00",)}
    assert protocol.ZONE_TARGET_ID not in values(ENUMERATION_ZONES_ANSWER)
    assert values("37fe200f0401910100") == {protocol.HEAT_REQUEST_ID: (b"\x01",)}


def test_no_values_from_other_sources():
    assert values("7ffe20100dc19402006996dc0000c2940200") == {}


def test_values_stop_at_an_id_of_unknown_width():
    assert values("37fe20100dc1940200d14001006996dc0000") == {bytes.fromhex("c194"): (b"\x02",)}


def test_writes_and_setting_queries_as_the_cube_sends_them():
    assert protocol.write(protocol.COMFORT_ID, protocol.encode_temperature(30.0)) == "fe2020046271" + "2c01"
    assert protocol.setting_query(protocol.COMFORT_ID) == "fe2001026271"


def test_slave_addresses_need_a_valid_master_address():
    assert protocol.is_slave_with_master(0x75)
    assert protocol.is_slave_with_master(0x3C)
    assert not protocol.is_slave_with_master(0x00)
    assert not protocol.is_slave_with_master(0xFE)
    assert not protocol.is_slave_with_master(0x70)
