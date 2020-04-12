#!/usr/bin/env python

# MMC5883MA is pin-to-pin compatible with HMC5883L but with lower noise and different reg map

import time
import traceback as tb

import collectd
from envsensor._smbus2 import SMBus

class MMC5883MA:
  # NOTE: MMC5883MA's address is always 0x30. Only 1 sensor can be on a bus unless an address translator is used.
  I2C_ADDR        = 0x30
  REG_DATA_X_LSB  = 0x00
  REG_DATA_X_MSB  = 0x01
  REG_DATA_Y_LSB  = 0x02
  REG_DATA_Y_MSB  = 0x03
  REG_DATA_Z_LSB  = 0x04
  REG_DATA_Z_MSB  = 0x05
  REG_TEMPERATURE = 0x06
  REG_STATUS      = 0x07
  REG_CONTROL_0   = 0x08
  REG_CONTROL_1   = 0x09
  REG_CONTROL_2   = 0x0a
  REG_X_THRESHOLD = 0x0b
  REG_Y_THRESHOLD = 0x0c
  REG_Z_THRESHOLD = 0x0d
  REG_ID_1        = 0x2f
  MICROTESLA_PER_LSB  = 100. / 4096 # 4096 counts per Guass
  # Datasheet states ~0.7 Celsius/LSB, 128 counts total from -75 to 125 Celsius, but this does not add up. It should be 256 counts.
  CELSIUS_PER_LSB     = (128 - (-75)) / 256
  CELSIUS_AT_ZERO_LSB = -75

  def __init__(self, busno = 1, address = I2C_ADDR, alpha = 0.0001):
    self.busno = busno
    self.bus = SMBus(busno)
    self.address = address
    chip_id = self.bus.read_byte_data(self.address, self.REG_ID_1)
    if chip_id != 0x0c:
      raise IOError('Invalid chip ID (0x{:02x})'.format(chip_id))
    self.reset()
    # default after reset: single measurement mode, 16-bit, 10 ms / 100 Hz BW, 0.04 uT noise
    self.measure_offset()
    self.alpha = alpha
    self.mean = self.read()

  def _convert_m(self, data, offset):
    val = data[offset + 1] << 8 | data[offset]
    # MMC5883MA always use full 16-bit range, unsigned, 0 at 32768
    return (val - (1 << 15)) * self.MICROTESLA_PER_LSB

  def read(self, set_reset = 0x00):
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, 0x01 | set_reset) # single measuremet for M
    time.sleep(0.02) # actual: 10 ms typical
    # NOTE: reading data will clear status, so we need to read it first
    status = self.bus.read_byte_data(self.address, self.REG_STATUS)
    if status & 0x01 != 0x01:
      raise IOError('Sensor not in RDY state (0x{:02x})'.format(status))
    base = self.REG_DATA_X_LSB
    length = self.REG_DATA_Z_MSB - base + 1
    data = self.bus.read_i2c_block_data(self.address, base, length)
    x = self._convert_m(data, self.REG_DATA_X_LSB - base) - self.offset[0]
    y = self._convert_m(data, self.REG_DATA_Y_LSB - base) - self.offset[1]
    z = self._convert_m(data, self.REG_DATA_Z_LSB - base) - self.offset[2]
    return x, y, z

  def measure_offset(self):
    self.offset = (0., 0., 0.)
    # SET the sensor with coil
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, 0x08)
    time.sleep(0.02) # should be a good idea to wait a bit for current to stablize
    x1, y1, z1 = self.read(0x08)
    # RESET the sensor with coil
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, 0x10)
    time.sleep(0.02)
    x2, y2, z2 = self.read(0x10)
    # Turn off coil
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, 0x00)
    self.offset = ((x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2)
    # Should be measured again if temperature changed a lot
    self.offset_t = self.read_temperature()

  def read_temperature(self):
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, 0x02) # single measuremet for T
    time.sleep(0.02) # actual: 10 ms typical
    # NOTE: reading data will clear status, so we need to read it first
    status = self.bus.read_byte_data(self.address, self.REG_STATUS)
    if status & 0x02 != 0x02:
      raise IOError('Sensor not in RDY state (0x{:02x})'.format(status))
    return (self.bus.read_byte_data(self.address, self.REG_TEMPERATURE) *
        self.CELSIUS_PER_LSB + self.CELSIUS_AT_ZERO_LSB)

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

  def reset(self):
    self.bus.write_byte_data(self.address, self.REG_CONTROL_1, 0x80)

buses   = []
sensors = []
alpha   = 0.0001

'''
Config example:

Import "envsensor.mmc5883ma"
<Module "envsensor.mmc5883ma">
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
      sensor = MMC5883MA(bus)
      sensors.append(sensor)
      collectd.info('{}: Initialized sensor on i2c-{}'.format(__name__, bus))
    except:
      collectd.error('{}: Failed to init sensor on i2c-{}:\n{}'.format(__name__, bus, tb.format_exc()))

def read(data = None):
  global sensors

  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'
  vl.type_instance = 'MMC5883MA'

  for sensor in sensors:
    try:
      t = sensor.read_temperature()
      vl.dispatch(type = 'temperature', type_instance = 'MMC5883MA', plugin_instance = 'i2c-{}'.format(sensor.busno), values = [t])
      x, y, z = sensor.read()
      vl.plugin_instance = 'i2c-{}_uT'.format(sensor.busno)
      vl.dispatch(type = 'gauge', type_instance = 'MMC5883MA_X', values = [x])
      vl.dispatch(type = 'gauge', type_instance = 'MMC5883MA_Y', values = [y])
      vl.dispatch(type = 'gauge', type_instance = 'MMC5883MA_Z', values = [z])

      # This should be feed at regular intervals
      dx, dy, dz = sensor.get_delta(x, y, z)
      vl.plugin_instance = 'i2c-{}_uT-delta'.format(sensor.busno)
      vl.dispatch(type = 'gauge', type_instance = 'MMC5883MA_X', values = [dx])
      vl.dispatch(type = 'gauge', type_instance = 'MMC5883MA_Y', values = [dy])
      vl.dispatch(type = 'gauge', type_instance = 'MMC5883MA_Z', values = [dz])
    except:
      collectd.error('{}: Failed to read magnetic field on i2c-{}:\n{}'.format(__name__, sensor.busno, tb.format_exc()))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
