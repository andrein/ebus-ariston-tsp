from conftest import rooms
import pytest

Room = rooms.Room
reported_temperature = rooms.reported_temperature


def test_the_neediest_room_sets_the_distance_from_the_zone_target():
    house = [Room(21.6, 22.0, True), Room(20.5, 21.0, True), Room(22.4, 22.0, True)]
    assert reported_temperature(house, 22.0, 5.0) == pytest.approx(21.5)


def test_rooms_above_their_target_report_above_the_zone_target():
    assert reported_temperature([Room(22.3, 22.0, True), Room(23.0, 22.0, True)], 22.0, 5.0) == pytest.approx(22.3)


def test_rooms_that_are_off_do_not_count():
    house = [Room(18.0, 22.0, False), Room(21.9, 22.0, True)]
    assert reported_temperature(house, 22.0, 5.0) == pytest.approx(21.9)


def test_every_room_off_reports_the_zone_target():
    assert reported_temperature([Room(18.0, 22.0, False)], 22.0, 5.0) == 22.0


def test_without_any_room_temperature_nothing_is_reported():
    assert reported_temperature([Room(None, 22.0, True)], 22.0, 5.0) is None
    assert reported_temperature([], 22.0, 5.0) is None


def test_without_the_zone_target_nothing_is_reported():
    assert reported_temperature([Room(21.0, 22.0, True)], None, 5.0) is None


def test_zone_at_its_frost_temperature_gets_the_coldest_real_room_also_from_rooms_that_are_off():
    house = [Room(4.2, 22.0, False), Room(6.0, 18.0, True)]
    assert reported_temperature(house, 5.0, 5.0) == 4.2
