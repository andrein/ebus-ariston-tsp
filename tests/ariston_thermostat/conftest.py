"""Loads the integration's pure modules without Home Assistant, which its __init__ imports."""

import importlib
from pathlib import Path
import sys
import types

_PACKAGE = "ariston_thermostat"
_package = types.ModuleType(_PACKAGE)
_package.__path__ = [str(Path(__file__).parents[2] / "custom_components" / _PACKAGE)]
sys.modules.setdefault(_PACKAGE, _package)

protocol = importlib.import_module(f"{_PACKAGE}.protocol")
room_sensor = importlib.import_module(f"{_PACKAGE}.room_sensor")
rooms = importlib.import_module(f"{_PACKAGE}.rooms")
ebusd = importlib.import_module(f"{_PACKAGE}.ebusd")
