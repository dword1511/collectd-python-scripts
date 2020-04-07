#!/usr/bin/env python

# This should support both BMP085 and BMP180, but only tested with BMP180
# NOTE: BMP085/BMP180's address is always 0x77. Only 1 sensor can be on a bus unless an address translator is used.

# TODO: config for I2C/SPI and mode?

import sys

import collectd
from envsensor._bmp085 import BMP085, BMP085_ULTRAHIGHRES

buses   = []
sensors = []

'''
Config example:

Import "envsensor.bmp180"
<Module "envsensor.bmp180">
  Buses       "1 2 3 5 7"
</Module>
'''
def config(config_in):
  global buses

  buses_set = False

  for node in config_in.children:
    key = node.key.lower()
    val = node.values[0]

    if key == 'buses':
      buses = val.lower().split()
      for i in range(len(buses)):
        try:
          buses[i] = int(buses[i], 10)
        except:
          collectd.error('{}: "{}" is not a valid number, skipping'.format(__name__, buses[i]))
      buses_set = True

    else:
      collectd.warning('{}: Skipping unknown config key {}'.format(__name__, node.key))

  if not buses_set:
    buses = [1]
    collectd.info('{}: Buses not set, defaulting to {}'.format(__name__, str(buses)))

def init():
  global sensors, buses

  collectd.debug('buses = ' + str(buses))

  for bus in buses:
    if bus is None:
      continue
    try:
      # On a host that can run collectd, anything other than the highest-resolution mode does not make sense
      sensor = BMP085(bus, mode = BMP085_ULTRAHIGHRES)
      sensors.append(sensor)
      collectd.info('{}: Initialized sensor on i2c-{}'.format(__name__, bus))
    except:
      collectd.error('{}: Failed to init sensor on i2c-{}: {}'.format(__name__, bus, str(sys.exc_info())))

def read(data = None):
  global sensors

  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'
  vl.type_instance = 'BMP180'

  for sensor in sensors:
    vl.plugin_instance = 'i2c-{}'.format(sensor.get_bus())
    try:
      temperature, pressure = sensor.read_tp()
    except:
      collectd.error('{}: Failed to read sensor on i2c-{}: {}'.format(__name__, sensor.get_bus(), str(sys.exc_info())))

    vl.dispatch(type = 'temperature', values = [temperature])
    vl.dispatch(type = 'pressure', values = [pressure])

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
