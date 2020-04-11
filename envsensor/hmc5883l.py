#!/usr/bin/env python

# Depends on: python-smbus

# Original HMC5883L code: https://github.com/rm-hull/hmc5883l/blob/master/hmc5883l.py
# TODO: sensitivity config? min/max line?

import time
import traceback as tb

import collectd
import smbus

class HMC5883L:
  # NOTE: HMC5883L's address is always 0x1e. Only 1 sensor can be on a bus unless an address translator is used.
  I2C_ADDR        = 0x1e
  REG_CONFIG_A    = 0x00
  REG_CONFIG_B    = 0x01
  REG_MODE        = 0x02
  REG_DATA_X_MSB  = 0x03
  REG_DATA_X_LSB  = 0x04
  REG_DATA_Z_MSB  = 0x05
  REG_DATA_Z_LSB  = 0x06
  REG_DATA_Y_MSB  = 0x07
  REG_DATA_Y_LSB  = 0x08
  REG_STATUS      = 0x09
  REG_ID_0        = 0x0a
  REG_ID_1        = 0x0b
  REG_ID_2        = 0x0c

  # {recommended range in +/- uT: [reg value, uT per LSB]}
  _range_ut_config = {
     88: [0, 0.073],
    130: [1, 0.092], # this is the default and should be the most reasonable for ambient magnetic field
    190: [2, 0.122],
    250: [3, 0.152],
    400: [4, 0.227],
    470: [5, 0.256],
    560: [6, 0.303],
    810: [7, 0.435],
  }

  def __init__(self, busno = 1, address = I2C_ADDR, range_ut = 130, alpha = 0.0001):
    self.busno = busno
    self.bus = smbus.SMBus(busno)
    self.address = address
    chip_id = self.bus.read_i2c_block_data(self.address, self.REG_ID_0, 3)
    if chip_id != [0x48, 0x34, 0x33]: # 'H43'
      raise IOError('Invalid chip ID (got {})'.format(str(chip_id)))
    self.bus.write_byte_data(self.address, self.REG_CONFIG_A, 0x70) # 8-average, 15 Hz, normal measurement
    self.set_range(range_ut)
    self.alpha = alpha
    self.mean = self.read()

  def set_range(self, range_ut):
    if range_ut not in self._range_ut_config.keys():
      raise ValueError('Invalid range {} uT, possible values: {}'.format(range_ut, _range_ut_config.keys()))
    reg, self._scale = self._range_ut_config[range_ut]
    self.bus.write_byte_data(self.address, self.REG_CONFIG_B, reg << 5)

  def _twos_complement(self, val, len):
    # Convert twos compliment to signed integer
    if (val & (1 << len - 1)):
      val = val - (1 << len)
    return val

  def _convert(self, data, offset):
    val = self._twos_complement(data[offset] << 8 | data[offset + 1], 16)
    if val == -4096:
      raise ValueError('Measurement overflowed (you may also need degaussing)')
    return val * self._scale

  def read(self):
    self.bus.write_byte_data(self.address, self.REG_MODE, 0x01) # single measurement
    time.sleep(0.01) # actual: 6 ms typical
    # NOTE: reading data will clear status, so we need to read it first
    status = self.bus.read_byte_data(self.address, self.REG_STATUS)
    if status != 0x01:
      raise IOError('Sensor not in RDY state (0x{:02x})'.format(status))
    base = self.REG_DATA_X_MSB
    length = self.REG_DATA_Y_LSB - self.REG_DATA_X_MSB + 1
    data = self.bus.read_i2c_block_data(self.address, base, length)
    x = self._convert(data, self.REG_DATA_X_MSB - base)
    y = self._convert(data, self.REG_DATA_Y_MSB - base)
    z = self._convert(data, self.REG_DATA_Z_MSB - base)
    return x, y, z

  def get_delta(self, x, y, z):
    # NOTE: when alpha = 1, this becomes sample-wise differential
    dx = x - self.mean[0]
    dy = y - self.mean[1]
    dz = z - self.mean[2]
    # Update LPF (first-order IIR)
    # Should use numpy, but that's another dependency
    mx = self.mean[0] * (1 - self.alpha) + x * self.alpha
    my = self.mean[1] * (1 - self.alpha) + y * self.alpha
    mz = self.mean[2] * (1 - self.alpha) + z * self.alpha
    self.mean = (mx, my, mz)
    return dx, dy, dz

buses   = []
sensors = []
alpha   = 0.0001

'''
Config example:

Import "envsensor.hmc5883l"
<Module "envsensor.hmc5883l">
  Buses       "1 2 3 5 7"
  Alpha       0.0001
</Module>

Alpha must be in the range (0, 1] and usually should be small
'''
def config(config_in):
  global buses

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
    elif key == 'alpha':
      try:
        arg = float(val)
        if arg <= 0. or arg > 1.:
          raise ValueError("alpha must be a float in the range (0, 1]")
        alpha = arg
      except:
        collectd.error('{}: "{}" is not a valid alpha value, using default'.format(__name__, val))
    else:
      collectd.warning('{}: Skipping unknown config key {}'.format(__name__, node.key))

def init():
  global sensors, buses

  if not buses:
    buses = [1]
    collectd.info('{}: Buses not set, defaulting to {}'.format(__name__, str(buses)))
  collectd.info('{}: Using alpha {} for delta'.format(__name__, alpha))

  for bus in buses:
    if bus is None:
      continue
    try:
      sensor = HMC5883L(bus)
      sensors.append(sensor)
      collectd.info('{}: Initialized sensor on i2c-{}'.format(__name__, bus))
    except:
      collectd.error('{}: Failed to init sensor on i2c-{}:\n{}'.format(__name__, bus, tb.format_exc()))

def read(data = None):
  global sensors

  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'
  vl.type_instance = 'HMC5883L'

  for sensor in sensors:
    try:
      x, y, z = sensor.read()
      vl.plugin_instance = 'i2c-{}_uT'.format(sensor.busno)
      vl.dispatch(type = 'gauge', type_instance = 'HMC5883L_X', values = [x])
      vl.dispatch(type = 'gauge', type_instance = 'HMC5883L_Y', values = [y])
      vl.dispatch(type = 'gauge', type_instance = 'HMC5883L_Z', values = [z])

      # This should be feed at regular intervals
      dx, dy, dz = sensor.get_delta(x, y, z)
      vl.plugin_instance = 'i2c-{}_uT-delta'.format(sensor.busno)
      vl.dispatch(type = 'gauge', type_instance = 'HMC5883L_X', values = [dx])
      vl.dispatch(type = 'gauge', type_instance = 'HMC5883L_Y', values = [dy])
      vl.dispatch(type = 'gauge', type_instance = 'HMC5883L_Z', values = [dz])
    except:
      collectd.error('{}: Failed to read magnetic field on i2c-{}:\n{}'.format(__name__, sensor.busno, tb.format_exc()))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
