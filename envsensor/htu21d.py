#!/usr/bin/env python

# Original HTU21D code: https://github.com/jasiek/HTU21D/
# Did not use adafruit-circuitpython-htu21d as it does not support python2

import time

import collectd
from envsensor._smbus2 import SMBus
from envsensor._utils import logi, logw, loge, i2c_rdwr_read, i2c_rdwr_write

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

  # Stuff hidden in the app note (HPC207_0 October 2012)
  CMD_READ_SN_1       = 0xfa
  CMD_READ_SN_2       = 0x0f
  CMD_READ_SN_3       = 0xfc
  CMD_READ_SN_4       = 0xc9
  SN_FIXED_FIELD      = 0x4854000000003200
  SN_FIXED_FIELD_MASK = 0xffffff000000ff00

  def __init__(self, busno, address = I2C_ADDR):
    self.busno = busno
    self.bus = SMBus(busno)
    self.address = address

  def read_serial(self):
    i2c_rdwr_write(self.bus, self.address, [self.CMD_READ_SN_1, self.CMD_READ_SN_2])
    response = i2c_rdwr_read(self.bus, self.address, 8)
    snb3, crc_snb3, snb2, crc_snb2, snb1, crc_snb1, snb0, crc_snb0 = response
    HTU21D.crc_check([snb3], crc_snb3)
    HTU21D.crc_check([snb2], crc_snb2)
    HTU21D.crc_check([snb1], crc_snb1)
    HTU21D.crc_check([snb0], crc_snb0)
    snb = (snb3 << 24) | (snb2 << 16) | (snb1 << 8) | snb0

    i2c_rdwr_write(self.bus, self.address, [self.CMD_READ_SN_3, self.CMD_READ_SN_4])
    response = i2c_rdwr_read(self.bus, self.address, 6)
    snc1, snc0, crc_snc, sna1, sna0, crc_sna = response
    HTU21D.crc_check([snc1, snc0], crc_snc)
    HTU21D.crc_check([sna1, sna0], crc_sna)
    snc = (snc1 << 8) | snc0
    sna = (sna1 << 8) | sna0

    sn = (sna << 48) | (snb << 16) | snc
    if sn & self.SN_FIXED_FIELD_MASK != self.SN_FIXED_FIELD:
      raise ValueError('S/N {:016x} is invalid for HTU21D'.format(sn))
    return sn

  def read_temperature(self):
    i2c_rdwr_write(self.bus, self.address, [self.CMD_TRIG_TEMP_NHM])
    time.sleep(0.06) # actual: 50 ms max
    msb, lsb, crc = i2c_rdwr_read(self.bus, self.address, 3)
    HTU21D.crc_check([msb, lsb], crc)
    return -46.85 + 175.72 * ((msb << 8) + lsb) / float(1 << 16)

  def read_humidity(self):
    i2c_rdwr_write(self.bus, self.address, [self.CMD_TRIG_HUMID_NHM])
    time.sleep(0.02) # actual: 16 ms max
    msb, lsb, crc = i2c_rdwr_read(self.bus, self.address, 3)
    HTU21D.crc_check([msb, lsb], crc)
    return -6 + 125 * ((msb << 8) + lsb) / float(1 << 16)

  def reset(self):
    i2c_rdwr_write(self.bus, self.address, [self.CMD_RESET])

  def crc_check(bytes, expected):
    computed = HTU21D.compute_crc(bytes)
    if computed != expected:
      raise IOError('Computed CRC 0x{:02x}, expected 0x{:02x}'.format(computed, expected))

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
  Buses       1 2 3 5 7
</Module>
'''
def config(config_in):
  global buses

  for node in config_in.children:
    key = node.key.lower()
    val = node.values[0]

    if key == 'buses':
      if isinstance(val, list):
        buses = val
      else:
        buses = [val]
      for i in range(len(buses)):
        try:
          buses[i] = int(buses[i])
        except:
          loge('"{}" is not a valid number, skipping'.format(buses[i]))
    else:
      logw('Skipping unknown config key "{}"'.format(key))

def init():
  global sensors, buses

  if not buses:
    buses = [1]
    logi('Buses not set, defaulting to {}'.format(str(buses)))

  for bus in buses:
    if bus is None:
      continue
    try:
      sensor = HTU21D(bus)
      sensor.reset()
      sn = sensor.read_serial()
      sensors.append(sensor)
      logi('Initialized sensor on i2c-{}, S/N: {:016x}'.format(bus, sn))
    except:
      loge('Failed to init sensor on i2c-{}'.format(bus))

def read(data = None):
  global sensors

  vl = collectd.Values(plugin = 'envsensor')
  vl.type_instance = 'HTU21D'
  for sensor in sensors:
    vl.plugin_instance = 'i2c-{}'.format(sensor.busno)

    try:
      vl.dispatch(type = 'temperature', values = [sensor.read_temperature()])
    except:
      loge('Failed to read temperature on i2c-{}'.format(sensor.busno))

    try:
      vl.dispatch(type = 'humidity', values = [sensor.read_humidity()])
    except:
      loge('Failed to read humidity on i2c-{}'.format(sensor.busno))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
