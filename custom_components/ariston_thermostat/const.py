DOMAIN = "ariston_thermostat"

CONF_SERIAL = "serial"
CONF_SLAVE = "slave"
CONF_SOURCE = "source"
CONF_SENSOR_ENTITY = "sensor_entity"
CONF_CLIMATE_ENTITIES = "climate_entities"

SOURCE_THERMOSTAT = "thermostat"
SOURCE_NEEDIEST_ROOM = "neediest_room"

DEFAULT_PORT = 8888
# The boiler does not check the serial: it registered and used the sensor with all zeros as with a real Cube's.
DEFAULT_SERIAL = "000000000000"
DEFAULT_SLAVE = "75"

# Well before the gateway resets the bus after ~27 min of unanswered room temperature queries.
DISCONNECTED_ISSUE_DELAY = 300
