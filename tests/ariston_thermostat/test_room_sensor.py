from conftest import protocol, room_sensor
from protocol_frames import (
    BOILER_QUERY,
    BOILER_RESET,
    BOILER_SETTINGS_CAST,
    BOILER_STATUS_CAST,
    COMFORT_ANSWER,
    ENUMERATION_ZONES_ANSWER,
    GATEWAY_QUERY,
    GATEWAY_RESET,
    HEAT_REQUEST_CAST,
    ROOM_SENSOR_MISSING,
)
import pytest

RoomSensor = room_sensor.RoomSensor
StreamLine = protocol.StreamLine
SERIAL = protocol.serial("262010629184", 0x75)


class Bus:
    def __init__(self, temperature=21.8):
        self.sent = []
        self.delays = {}
        self.temperature = temperature
        self.sensor = RoomSensor(self.send, lambda: self.temperature, "262010629184", 0x75)

    def send(self, message, delay):
        self.sent.append(message)
        self.delays[message] = delay

    def receive(self, frame, now, timestamp=1000.0, kind="r"):
        self.sensor.on_line(StreamLine(timestamp, kind, protocol.Frame.parse(frame)), now)


ADDRESS_CAST = protocol.address_cast(0x75)
SETTING_QUERIES = [
    protocol.setting_query(protocol.COMFORT_ID),
    protocol.setting_query(protocol.ZONE_MODE_ID),
    protocol.setting_query(protocol.FROST_ID),
    protocol.value_query(protocol.HEAT_REQUEST_ID),
]


def without_setting_queries(sent):
    return [message for message in sent if message not in SETTING_QUERIES]


def start_unknown(bus, now):
    """Start the sensor at `now` and keep only its address cast, which an unknown sensor gets a bus reset for."""
    bus.sensor.start(now)
    bus.sensor.tick(now)
    bus.sent = [message for message in bus.sent if message == ADDRESS_CAST]


def registered_bus():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 0.2)
    bus.receive(BOILER_QUERY, 30)
    bus.sent.clear()
    return bus


def test_unknown_sensor_answers_each_reset_of_the_enumeration_with_its_serial():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 0.2)
    bus.receive(BOILER_RESET, 2.1)
    assert bus.sent == [ADDRESS_CAST, SERIAL, SERIAL]
    assert not bus.sensor.registered


def test_first_query_registers_and_is_answered():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 0.2)
    bus.receive(BOILER_QUERY, 30)
    assert bus.sent[-1] == protocol.room_temperature_answer(21.8)
    assert bus.sensor.registered
    assert bus.sensor.statistics.registrations == 1
    assert bus.sensor.reported_temperature == 21.8


def test_registered_sensor_casts_its_temperature_and_address():
    bus = registered_bus()
    bus.sensor.tick(room_sensor.CAST_INTERVAL - 1)
    assert bus.sent == []
    bus.sensor.tick(room_sensor.CAST_INTERVAL)
    assert bus.sent == [protocol.room_temperature_cast(21.8)]
    bus.sensor.tick(330)
    assert bus.sent[-1] == "fe203b0175"


def test_no_address_cast_while_unregistered_but_the_first():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 1)
    for now in range(5, 1000, 5):
        bus.sensor.tick(now)
    assert bus.sent.count(ADDRESS_CAST) == 1


def test_gateway_query_is_answered_with_the_current_temperature():
    bus = registered_bus()
    bus.temperature = 20.04
    bus.receive(GATEWAY_QUERY, 200)
    assert bus.sent == [protocol.room_temperature_answer(20.0)]
    assert bus.sensor.statistics.queries_answered == 2


@pytest.mark.parametrize(("temperature", "reported"), [(80, 35.0), (3.04, 3.0), (-4, 0.0)])
def test_temperature_is_clamped(temperature, reported):
    bus = registered_bus()
    bus.temperature = temperature
    bus.receive(BOILER_QUERY, 100)
    assert bus.sent == [protocol.room_temperature_answer(reported)]


def test_latency_from_query_to_our_answer_on_the_bus():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_QUERY, 30, timestamp=1000.000)
    bus.receive("70" + protocol.room_temperature_answer(21.8), 30, timestamp=1000.085, kind="s")
    assert bus.sensor.statistics.answer_latency_ms == pytest.approx(85)


def test_failed_sends_are_counted():
    bus = registered_bus()
    bus.receive("70" + protocol.room_temperature_answer(21.8), 40, kind="e")
    assert bus.sensor.statistics.send_failures == 1


def test_failed_answer_is_sent_again_once():
    bus = registered_bus()
    answer = protocol.room_temperature_answer(21.8)
    bus.receive(BOILER_QUERY, 40)
    bus.sent.clear()
    bus.receive("70" + answer, 40, kind="e")
    bus.receive("70" + answer, 40, kind="e")
    assert bus.sent == [answer]
    bus.receive(BOILER_QUERY, 50)
    bus.receive("70" + answer, 50, kind="e")
    assert bus.sent == [answer, answer, answer]


def test_bus_reset_unregisters_until_the_next_query():
    bus = registered_bus()
    bus.receive(BOILER_RESET, 500)
    assert not bus.sensor.registered and bus.sent == [SERIAL]
    bus.receive(BOILER_QUERY, 520)
    assert bus.sensor.registered and bus.sensor.statistics.registrations == 2


def test_registration_is_retried_after_a_timeout_then_given_up():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 0)
    now = 0
    for _ in range(room_sensor.REGISTRATION_ATTEMPTS):
        now += room_sensor.REGISTRATION_TIMEOUT
        bus.sensor.tick(now)
        now += room_sensor.REGISTRATION_RETRY
        bus.sensor.tick(now)
    assert not bus.sensor.registration_failed
    bus.sensor.tick(now + room_sensor.REGISTRATION_TIMEOUT)
    resets = [message for message in bus.sent if message == "fe203400"]
    assert len(resets) == room_sensor.REGISTRATION_ATTEMPTS
    assert bus.sensor.registration_failed


def test_started_sensor_casts_and_answers_without_a_bus_reset():
    bus = Bus()
    bus.sensor.start(0)
    bus.sensor.tick(5)
    assert without_setting_queries(bus.sent) == [protocol.room_temperature_cast(21.8), ADDRESS_CAST]
    bus.receive(GATEWAY_QUERY, 10)
    assert bus.sent[-1] == protocol.room_temperature_answer(21.8)
    assert bus.sensor.registered


def test_foreign_reset_without_query_does_not_start_our_own_resets():
    bus = Bus()
    bus.sensor.start(0)
    bus.receive(GATEWAY_RESET, 10)
    for now in range(15, 4 * 3600, 5):
        bus.sensor.tick(now)
    assert "fe203400" not in bus.sent


def test_foreign_reset_cancels_a_pending_retry():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 0)
    bus.sensor.tick(room_sensor.REGISTRATION_TIMEOUT)  # retry at 690
    bus.receive(GATEWAY_RESET, 650)
    bus.sensor.tick(700)
    assert "fe203400" not in bus.sent


def test_error_411_re_registers_once():
    bus = registered_bus()
    bus.receive(ROOM_SENSOR_MISSING, 100)
    bus.receive(ROOM_SENSOR_MISSING, 110)
    assert bus.sent == ["fe203400"]


def test_failed_answer_does_not_distort_the_next_latency():
    bus = registered_bus()
    bus.receive(BOILER_QUERY, 40, timestamp=2000.0)
    bus.receive("70" + protocol.room_temperature_answer(21.8), 40, timestamp=2000.2, kind="e")
    bus.receive(BOILER_QUERY, 50, timestamp=2010.0)
    bus.receive("70" + protocol.room_temperature_answer(21.8), 50, timestamp=2010.05, kind="s")
    assert bus.sensor.statistics.answer_latency_ms == pytest.approx(50)


def test_serial_latency_from_reset_to_our_serial_on_the_bus():
    bus = Bus()
    bus.sensor.start(0)
    bus.receive(BOILER_RESET, 1, timestamp=3000.0)
    bus.receive("70" + SERIAL, 1, timestamp=3000.12, kind="s")
    assert bus.sensor.statistics.serial_latency_ms == pytest.approx(120)


def test_serial_is_sent_after_the_cube_delay():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 0.2)
    assert bus.delays[SERIAL] == room_sensor.SERIAL_DELAY


def test_reset_storm_stops_the_sensor():
    bus = Bus()
    start_unknown(bus, 0)
    for i in range(room_sensor.STORM_RESETS + 1):
        bus.receive(BOILER_RESET, 1 + i * 0.3)
    assert not bus.sensor.enabled and bus.sensor.storm_stopped
    assert bus.sent.count(SERIAL) == room_sensor.STORM_RESETS
    bus.receive(BOILER_RESET, 5)
    assert bus.sent.count(SERIAL) == room_sensor.STORM_RESETS


def test_resets_spread_over_time_are_not_a_storm():
    bus = Bus()
    start_unknown(bus, 0)
    for i in range(20):
        bus.receive(BOILER_RESET, i * 15)
    assert bus.sensor.enabled


def test_zone_state_from_the_boiler_also_before_starting():
    bus = Bus()
    for frame in (
        BOILER_STATUS_CAST,
        ENUMERATION_ZONES_ANSWER,
        BOILER_SETTINGS_CAST,
        COMFORT_ANSWER,
        HEAT_REQUEST_CAST,
    ):
        bus.receive(frame, 1)
    assert bus.sensor.zone == room_sensor.Zone(
        target=22.0, comfort=22.0, comfort_min=10.0, comfort_max=30.0, mode=2, heat_request=True, frost=5.0
    )
    assert bus.sent == []


def thermostat_bus():
    bus = Bus()
    bus.sensor = RoomSensor(bus.send, lambda: bus.temperature, "262010629184", 0x75, thermostat=True)
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 0.2)
    bus.receive(BOILER_QUERY, 30)
    bus.sent.clear()
    return bus


def test_thermostat_asks_for_its_settings_once_started_and_then_periodically():
    bus = Bus()
    bus.sensor = RoomSensor(bus.send, lambda: bus.temperature, "262010629184", 0x75, thermostat=True)
    bus.sensor.start(1000)
    bus.sensor.tick(1000)
    assert [m for m in bus.sent if m in SETTING_QUERIES] == SETTING_QUERIES
    bus.sent.clear()
    bus.sensor.tick(1000 + room_sensor.SETTINGS_INTERVAL - 1)
    assert not [m for m in bus.sent if m in SETTING_QUERIES]
    bus.sensor.tick(1000 + room_sensor.SETTINGS_INTERVAL)
    assert [m for m in bus.sent if m in SETTING_QUERIES] == SETTING_QUERIES


def test_room_sensor_alone_asks_for_settings_only_until_the_zone_target_and_frost_temperature_are_known():
    bus = Bus()
    bus.sensor.start(0)
    bus.sensor.tick(0)
    # The heat request only shows on the thermostat entity.
    assert [m for m in bus.sent if m in SETTING_QUERIES] == SETTING_QUERIES[:3]
    bus.receive(BOILER_STATUS_CAST, 1)
    bus.sent.clear()
    bus.sensor.tick(room_sensor.SETTINGS_INTERVAL)
    assert [m for m in bus.sent if m in SETTING_QUERIES] == SETTING_QUERIES[:3]
    bus.receive(BOILER_SETTINGS_CAST, 2)
    bus.sent.clear()
    bus.sensor.tick(2 * room_sensor.SETTINGS_INTERVAL)
    assert not [m for m in bus.sent if m in SETTING_QUERIES]


def test_writes_are_checked_by_asking_again():
    bus = thermostat_bus()
    bus.sensor.set_comfort(21.5)
    bus.sensor.set_zone_mode(3)
    write_comfort = protocol.write(protocol.COMFORT_ID, protocol.encode_temperature(21.5))
    write_mode = protocol.write(protocol.ZONE_MODE_ID, b"\x03")
    assert bus.sent == [write_comfort, SETTING_QUERIES[0], write_mode, SETTING_QUERIES[1]]
    assert bus.delays[SETTING_QUERIES[0]] == room_sensor.WRITE_CHECK_DELAY


def test_known_sensor_is_registered_when_its_address_cast_triggers_nothing():
    bus = Bus()
    start_unknown(bus, 0)
    bus.sensor.tick(room_sensor.PROBE_WINDOW - 1)
    assert not bus.sensor.registered
    bus.sensor.tick(room_sensor.PROBE_WINDOW)
    assert bus.sensor.registered
    assert bus.sent == [ADDRESS_CAST]


def test_enumeration_after_the_address_cast_without_query_falls_back_to_our_own_registration():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive(BOILER_RESET, 1)
    bus.sensor.tick(1 + room_sensor.REGISTRATION_TIMEOUT)
    assert "fe203400" not in bus.sent
    bus.sensor.tick(1 + room_sensor.REGISTRATION_TIMEOUT + room_sensor.REGISTRATION_RETRY)
    assert "fe203400" in bus.sent


def test_lost_track_checks_again_with_an_address_cast():
    bus = registered_bus()
    bus.sensor.lost_track()
    bus.sensor.tick(31)
    assert ADDRESS_CAST in bus.sent


def test_stopped_sensor_neither_answers_nor_registers():
    bus = Bus()
    start_unknown(bus, 0)
    for i in range(room_sensor.STORM_RESETS + 1):
        bus.receive(BOILER_RESET, 1 + i * 0.3)
    bus.sent.clear()
    bus.receive(BOILER_QUERY, 10)
    for now in range(15, 4 * 3600, 5):
        bus.sensor.tick(now)
    assert bus.sent == []


def test_nothing_is_reported_until_the_temperature_is_known():
    bus = Bus(temperature=None)
    bus.sensor.start(0)
    bus.receive(GATEWAY_QUERY, 1)
    bus.sensor.tick(5)
    assert without_setting_queries(bus.sent) == []
    assert bus.sensor.reported_temperature is None
    bus.temperature = 21.5
    bus.sensor.tick(10)
    assert without_setting_queries(bus.sent) == [protocol.room_temperature_cast(21.5)]


def test_failed_address_cast_is_sent_again():
    bus = Bus()
    start_unknown(bus, 0)
    bus.receive("70" + ADDRESS_CAST, 0, kind="e")
    bus.sensor.tick(room_sensor.PROBE_WINDOW)
    assert not bus.sensor.registered
    assert bus.sent == [ADDRESS_CAST, ADDRESS_CAST]


def test_missing_temperature_keeps_the_last_one_until_stale_then_the_sensor_goes_silent():
    bus = registered_bus()
    bus.temperature = None
    bus.receive(BOILER_QUERY, 100)
    assert bus.sent == [protocol.room_temperature_answer(21.8)]
    bus.sensor.tick(30 + room_sensor.STALE_AFTER - 1)
    assert not bus.sensor.silent and bus.sensor.reported_temperature == 21.8
    bus.sensor.tick(30 + room_sensor.STALE_AFTER)
    assert bus.sensor.silent and not bus.sensor.registered
    assert bus.sensor.reported_temperature is None
    bus.sent.clear()
    bus.receive(BOILER_QUERY, 700)
    bus.receive(BOILER_RESET, 710)
    bus.receive(ROOM_SENSOR_MISSING, 720)
    for now in range(725, 2000, 5):
        bus.sensor.tick(now)
    assert without_setting_queries(bus.sent) == []


def test_silent_sensor_comes_back_with_its_temperature_and_checks_its_registration():
    bus = registered_bus()
    bus.temperature = None
    bus.sensor.tick(30 + room_sensor.STALE_AFTER)
    bus.sent.clear()
    bus.temperature = 21.0
    bus.sensor.tick(2000)
    assert not bus.sensor.silent
    assert without_setting_queries(bus.sent) == [protocol.room_temperature_cast(21.0), ADDRESS_CAST]


def test_sensor_without_any_temperature_goes_silent():
    bus = Bus(temperature=None)
    bus.sensor.start(0)
    bus.sensor.tick(room_sensor.STALE_AFTER - 1)
    assert not bus.sensor.silent
    bus.sensor.tick(room_sensor.STALE_AFTER)
    assert bus.sensor.silent
