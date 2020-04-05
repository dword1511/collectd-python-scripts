#!/usr/bin/env python

# Original HTU21D code: https://github.com/jasiek/HTU21D/
# Did not use adafruit-circuitpython-htu21d as it does not support python2
# Did not use smbus/smbus2 because they cannot do certain I2C transactions

import time

import collectd
from envsensor._i2cdev import I2C

class HTU21D:
  # NOTE: HTU21D's address is always 0x40. Only 1 sensor can be on a bus unless an address translator is used.
  I2C_ADDR            = 0x40
  CMD_TRIG_TEMP_HM    = 0xe3
  CMD_TRIG_HUMID_HM   = 0xe5
  CMD_TRIG_TEMP_NHM   = 0xf3
  CMD_TRIG_HUMID_NHM  = 0xf5
  CMD_WRITE_USER_REG  = 0xe6
  CMD_READ_USER_REG   = 0xe7
  CMD_RESET           = 0xfe

  def __init__(self, busno):
    self.busno = busno
    self.bus = I2C(busno)
    self.bus.set_addr(self.I2C_ADDR)

  def __del__(self):
    self.bus.close()

  def read_temperature(self):
    self.bus.write([self.CMD_TRIG_TEMP_NHM])
    time.sleep(0.1)
    msb, lsb, crc = self.bus.read(3)
    crc_computed = HTU21D.compute_crc([msb, lsb])
    if crc != crc_computed:
      raise IOError('expected CRC 0x{:02x}, got 0x{:02x}'.format(crc_computed, crc))
    return -46.85 + 175.72 * ((msb << 8) + lsb) / float(1 << 16)

  def read_humidity(self):
    self.bus.write([self.CMD_TRIG_HUMID_NHM])
    time.sleep(0.1)
    msb, lsb, crc = self.bus.read(3)
    crc_computed = HTU21D.compute_crc([msb, lsb])
    if crc != crc_computed:
      raise IOError('expected CRC 0x{:02x}, got 0x{:02x}'.format(crc_computed, crc))
    return -6 + 125 * ((msb << 8) + lsb) / float(1 << 16)

  def reset(self):
    self.bus.write([self.CMD_RESET])

  def compute_crc(bytes):
    poly = 0x131
    crc = 0
    for byte in bytes:
      crc ^= byte
      for bit in range(8, 0, -1):
        if (crc & 0x80):
          crc = (crc << 1) ^ poly
        else:
          crc = (crc << 1)
    return crc

buses   = []
sensors = []

'''
Config example:

Import "envsensor.htu21d"
<Module "envsensor.htu21d">
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
      sensor = HTU21D(bus)
      sensor.reset()
      sensors.append(sensor)
      collectd.info('{}: Initialized sensor on i2c-{}'.format(__name__, bus))
    except:
      collectd.error('{}: Failed to init sensor on i2c-{}: {}'.format(__name__, bus, str(sys.exc_info())))

def read(data = None):
  global sensors

  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'
  vl.type_instance = 'HTU21D'

  for sensor in sensors:
    vl.plugin_instance = 'i2c-{}'.format(sensor.busno)
    try:
      vl.dispatch(type = 'temperature', values = [sensor.read_temperature()])
    except:
      collectd.error('{}: Failed to read temperature on i2c-{}: {}'.format(__name__, sensor.busno, str(sys.exc_info())))

    try:
      vl.dispatch(type = 'humidity', values = [sensor.read_humidity()])
    except:
      collectd.error('{}: Failed to read humidity on i2c-{}: {}'.format(__name__, sensor.busno, str(sys.exc_info())))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
