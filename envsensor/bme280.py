#!/usr/bin/env python

# Depends on: python-smbus

# TODO: config for I2C/SPI and mode?

import traceback as tb

import collectd
from envsensor._bme280 import BME280, BME280_I2CADDR_HI, BME280_I2CADDR_LO

buses_hiaddr  = []
buses_loaddr  = []
sensors       = []

'''
Config example:

Import "envsensor.bme280"
<Module "envsensor.bme280">
  Buses       "1 2 3 5 7L"
</Module>

Appending L to bus number will cause address 0x76 instead of 0x77 to be used.
'''
def config(config_in):
  global buses_hiaddr, buses_loaddr

  for node in config_in.children:
    key = node.key.lower()
    val = node.values[0]

    if key == 'buses':
      buses = val.lower().split()
      for i in range(len(buses)):
        try:
          if buses[i].endswith('l'):
            buses[i] = buses[i][:-1]
            buses_loaddr.append(int(buses[i], 10))
          else:
            buses_hiaddr.append(int(buses[i], 10))
        except ValueError:
          collectd.error('{}: "{}" is not a valid number, skipping'.format(__name__, buses[i]))
    else:
      collectd.warning('{}: Skipping unknown config key {}'.format(__name__, node.key))

def _init_one_sensor(sensors, bus, address):
  try:
    sensor = BME280(bus, address = address)
    sensors.append(sensor)
    collectd.info(
        '{}: Initialized sensor on i2c-{}, address 0x{:02x}'.format(__name__, bus, address))
  except:
    collectd.error(
        '{}: Failed to init sensor on i2c-{}, address 0x{:02x}: {}'
            .format(__name__, bus, address, tb.format_exc()))

def init():
  global sensors, buses_hiaddr, buses_loaddr

  if not buses_hiaddr and not buses_loaddr:
    buses_hiaddr = [1]
    collectd.info(
        '{}: Buses not set, defaulting to {}, address 0x{:02x}'
            .format(__name__, str(buses_hiaddr), BME280_I2CADDR_HI))

  for bus in buses_hiaddr:
    if bus is None:
      continue
    else:
      _init_one_sensor(sensors, bus, BME280_I2CADDR_HI)
  for bus in buses_loaddr:
    if bus is None:
      continue
    else:
      _init_one_sensor(sensors, bus, BME280_I2CADDR_LO)

def read(data = None):
  global sensors

  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'
  vl.type_instance = 'BME280'

  for sensor in sensors:
    vl.plugin_instance = 'i2c-{}'.format(sensor.get_bus())
    # NOTE: temperature must be read first
    try:
      temperature = sensor.read_temperature()
      vl.dispatch(type = 'temperature', values = [temperature])
    except:
      collectd.error(
          '{}: Failed to read temperature on i2c-{}, address 0x{:02x}: {}'
              .format(__name__, sensor.get_bus(), sensor.get_address(), tb.format_exc()))
    try:
      humidity = sensor.read_humidity()
      vl.dispatch(type = 'humidity', values = [humidity])
    except:
      collectd.error(
          '{}: Failed to read humidity on i2c-{}, address 0x{:02x}: {}'
              .format(__name__, sensor.get_bus(), sensor.get_address(), tb.format_exc()))
    try:
      pressure = sensor.read_pressure()
      vl.dispatch(type = 'pressure', values = [pressure])
    except:
      collectd.error(
          '{}: Failed to read pressure on i2c-{}, address 0x{:02x}: {}'
              .format(__name__, sensor.get_bus(), sensor.get_address(), tb.format_exc()))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
