import time

from envsensor._smbus2 import SMBus
from envsensor._utils import get_i2c_bus_number, get_word_le

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
    # discontinuities (jumps) in data
    x, y, z = self._read_magnetic()
    return {
      'X' : {
        'value' : x,
        'type'  : 'magnetic',
      },
      'Y' : {
        'value' : y,
        'type'  : 'magnetic',
      },
      'Z' : {
        'value' : z,
        'type'  : 'magnetic',
      },
      'die' : {
        'value' : t,
        'type'  : 'thermal',
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
