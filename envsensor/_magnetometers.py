import time

from envsensor._smbus2 import SMBus
from envsensor._utils import get_i2c_bus_number, get_word_le, get_word_be, twos_complement

class HMC5883L:
  '''
  Driver for Honeywell HMC5883L 3-axis magnetometer. This magnetometer uses AMR and is more
  sensitive than Hall magnetometers commonly found in smartphones.

  HMC5883L's address is always 0x1e. Only 1 sensor can be on a bus unless an address translator is
  used.
  '''

  I2C_ADDR        = 0x1e
  REG_CONFIG_A    = 0x00
  REG_CONFIG_B    = 0x01
  REG_MODE        = 0x02
  MODE_I2C_HS     = 1 << 7
  REG_DATA_X_MSB  = 0x03
  REG_DATA_X_LSB  = 0x04
  REG_DATA_Z_MSB  = 0x05
  REG_DATA_Z_LSB  = 0x06
  REG_DATA_Y_MSB  = 0x07
  REG_DATA_Y_LSB  = 0x08
  REG_STATUS      = 0x09
  STATUS_LOCK     = 1 << 1
  STATUS_RDY      = 1 << 0
  REG_ID_0        = 0x0a
  REG_ID_1        = 0x0b
  REG_ID_2        = 0x0c
  DEVICE_ID       = [0x48, 0x34, 0x33] # 'H43'

  # Controls averaging in config register A
  _average_config = {
    1: 0x0 << 5,
    2: 0x1 << 5,
    4: 0x2 << 5,
    8: 0x3 << 5,
  }

  # Controls data output rate in config register A
  _rate_config = {
    0.75: 0x0 << 2,
    1.5 : 0x1 << 2,
    3   : 0x2 << 2,
    7.5 : 0x3 << 2,
    15  : 0x4 << 2, # default
    30  : 0x5 << 2,
    75  : 0x6 << 2,
  }

  # Controls measurement bias mode in config register A
  _bias_config = {
    'normal'  : 0x0 << 0, # default
    'positive': 0x1 << 0, # biased
    'negative': 0x2 << 0, # biased
  }

  # Controls gain/range in config register B
  # {recommended range in +/- uT: (reg value, uT per LSB)}
  _range_config = {
     88: (0x0 << 5, 0.073),
    130: (0x1 << 5, 0.092), # default, also the most reasonable for ambient magnetic field
    190: (0x2 << 5, 0.122),
    250: (0x3 << 5, 0.152),
    400: (0x4 << 5, 0.227),
    470: (0x5 << 5, 0.256),
    560: (0x6 << 5, 0.303),
    810: (0x7 << 5, 0.435),
  }

  # Controls operating mode in mode register
  _mode_config = {
    'continuous': 0x0 << 0,
    'single'    : 0x1 << 0, # default
    'idle'      : 0x2 << 0, # can also be 0x3
  }

  def __init__(self, bus, address = I2C_ADDR):
    self.bus = SMBus(get_i2c_bus_number(bus))
    self.address = address

    # Verify device ID
    chip_id = self.bus.read_i2c_block_data(self.address, self.REG_ID_0, 3)
    if chip_id != self.DEVICE_ID:
      raise IOError(
          'Invalid device ID ({})'.format(' '.join(['0x{:02x}'.format(b) for b in chip_id])))

    # 8-average, 15 Hz, normal measurement
    self.bus.write_byte_data(
        self.address,
        self.REG_CONFIG_A,
        self._average_config[8] | self._rate_config[15] | self._bias_config['normal'])
    # TODO: range config and AGC?
    self._set_range(130)

  def read_channels(self):
    self.bus.write_byte_data(self.address, self.REG_MODE, self._mode_config['single'])
    time.sleep(0.01) # actual: 6 ms typical
    # NOTE: reading data will clear status, so we need to read it first
    if self.bus.read_byte_data(self.address, self.REG_STATUS) != self.STATUS_RDY:
      raise IOError('Sensor measurement timeout')

    base = self.REG_DATA_X_MSB
    length = self.REG_DATA_Y_LSB - self.REG_DATA_X_MSB + 1
    data = self.bus.read_i2c_block_data(self.address, base, length)
    x = self._convert_m(data, self.REG_DATA_X_MSB, base)
    y = self._convert_m(data, self.REG_DATA_Y_MSB, base)
    z = self._convert_m(data, self.REG_DATA_Z_MSB, base)
    return {
      'magnetic': {
        'X' : x,
        'Y' : y,
        'Z' : z,
      },
    }

  def _convert_m(self, data, offset, base):
    val = twos_complement(get_word_be(data, offset, base), 16)
    if val == -4096:
      raise ValueError('Measurement overflowed (you may also need degaussing)')
    return val * self._scale

  def _set_range(self, range_ut):
    if range_ut not in self._range_config.keys():
      raise ValueError(
          'Invalid range {} uT, possible values: {}'.format(range_ut, self._range_config.keys()))
    reg, self._scale = self._range_config[range_ut]
    self.bus.write_byte_data(self.address, self.REG_CONFIG_B, reg)

class MMC5883MA:
  '''
  Driver for MEMSIC MMC5883MA 3-axis magnetometer, which is pin-to-pin compatible with HMC5883L but
  with different I2C address and register map. Like HMC5883L, this sensor is AMR-based, but it has
  higher sensitivity and lower noise than the HMC5883L. It also has a temperature sensor on-die.

  MMC5883MA's address is always 0x30. Only 1 sensor can be on a bus unless an address translator is
  used.
  '''

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
  CONTROL_0_TM_M  = 1 << 0
  CONTROL_0_TM_T  = 1 << 1
  CONTROL_0_SET   = 1 << 3
  CONTROL_0_RESET = 1 << 4
  REG_CONTROL_1   = 0x09
  CONTROL_1_RST   = 1 << 7
  REG_CONTROL_2   = 0x0a
  REG_X_THRESHOLD = 0x0b
  REG_Y_THRESHOLD = 0x0c
  REG_Z_THRESHOLD = 0x0d
  REG_ID_1        = 0x2f
  CHIP_ID         = 0x0c

  MICROTESLA_PER_LSB  = 100. / 4096 # 4096 counts per Guass
  # Datasheet states ~0.7 Celsius/LSB, 128 counts total from -75 to 125 Celsius, but this does not
  # add up. It should be 256 counts.
  CELSIUS_PER_LSB     = (125 - (-75)) / 256
  CELSIUS_AT_ZERO_LSB = -75

  def __init__(self, bus, address = I2C_ADDR):
    self.bus = SMBus(get_i2c_bus_number(bus))
    self.address = address

    # Verify chip ID
    chip_id = self.bus.read_byte_data(self.address, self.REG_ID_1)
    if chip_id != self.CHIP_ID:
      raise IOError('Invalid chip ID (0x{:02x})'.format(chip_id))

    # Defaults after reset: single measurement mode, 16-bit, 10 ms / 100 Hz BW, 0.04 uT noise.
    # This seems to be the most suitable for ambient magnetic field.
    self.bus.write_byte_data(self.address, self.REG_CONTROL_1, self.CONTROL_1_RST)
    self._measure_offset()

  def read_channels(self):
    t = self._read_thermal()
    # TODO: offset should be measured again if temperature changed a lot, but this could introduce
    # discontinuities (jumps) in data (so probably run LPF over offset)
    x, y, z = self._read_magnetic()
    return {
      'magnetic': {
        'X' : x,
        'Y' : y,
        'Z' : z,
      },
      'thermal' : {
        ''  : t,
      },
    }

  def _measure_offset(self):
    self.offset = (0., 0., 0.)
    self.offset_temperature = self._read_thermal()
    # SET the sensor with coil
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, self.CONTROL_0_SET)
    time.sleep(0.02) # should be a good idea to wait a bit for current to stabilize
    x1, y1, z1 = self._read_magnetic(self.CONTROL_0_SET)
    # RESET the sensor with coil
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, self.CONTROL_0_RESET)
    time.sleep(0.02)
    x2, y2, z2 = self._read_magnetic(self.CONTROL_0_RESET)
    # Turn off coil
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, 0x00)
    self.offset = ((x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2)

  def _convert_m(self, data, offset):
    # MMC5883MA always use full 16-bit range, unsigned, 0 at 32768
    return (get_word_le(data, offset) - (1 << 15)) * self.MICROTESLA_PER_LSB

  def _read_magnetic(self, set_reset = 0x00):
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, self.CONTROL_0_TM_M | set_reset)
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

  def _read_thermal(self):
    self.bus.write_byte_data(self.address, self.REG_CONTROL_0, self.CONTROL_0_TM_T)
    time.sleep(0.02) # actual: 10 ms typical
    # NOTE: reading data will clear status, so we need to read it first
    status = self.bus.read_byte_data(self.address, self.REG_STATUS)
    if status & 0x02 != 0x02:
      raise IOError('Sensor not in RDY state (0x{:02x})'.format(status))
    return (self.bus.read_byte_data(self.address, self.REG_TEMPERATURE) *
        self.CELSIUS_PER_LSB + self.CELSIUS_AT_ZERO_LSB)
