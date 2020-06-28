#!/usr/bin/env python

import time

import collectd
from envsensor._smbus2 import SMBus
from envsensor._utils import logi, logw, loge, get_word_be, twos_complement, get_24bit_be

class DPS310:
  # DPS310's address is 0x77 by default, or 0x76 if SDO pulled down (unless a translator is used).
  I2C_ADDR                = 0x77

  REG_PRS_B2              = 0x00
  REG_PRS_B1              = 0x01
  REG_PRS_B0              = 0x02
  REG_TMP_B2              = 0x03
  REG_TMP_B1              = 0x04
  REG_TMP_B0              = 0x05
  REG_PRS_CFG             = 0x06
  PRS_CFG_PM_RATE_1HZ     = 0 << 4
  PRS_CFG_PM_RATE_2HZ     = 1 << 4
  PRS_CFG_PM_RATE_4HZ     = 2 << 4 # Highest rate allowing all oversampling
  PRS_CFG_PM_RATE_8HZ     = 3 << 4 # Highest rate allowing high precision mode
  PRS_CFG_PM_RATE_16HZ    = 4 << 4
  PRS_CFG_PM_RATE_32HZ    = 5 << 4
  PRS_CFG_PM_RATE_64HZ    = 6 << 4
  PRS_CFG_PM_RATE_128HZ   = 7 << 4
  # NOTE: measurement time is roughly 1.6 ms * oversampling + 2 ms
  PRS_CFG_PM_PRC_1X       = 0 << 0
  PRS_CFG_PM_PRC_2X       = 1 << 0 # Low power
  PRS_CFG_PM_PRC_4X       = 2 << 0
  PRS_CFG_PM_PRC_8X       = 3 << 0
  PRS_CFG_PM_PRC_16X      = 4 << 0 # Standard, needs bit shift
  PRS_CFG_PM_PRC_32X      = 5 << 0 # Needs bit shift
  PRS_CFG_PM_PRC_64X      = 6 << 0 # High precision, needs bit shift
  PRS_CFG_PM_PRC_128X     = 7 << 0 # Needs bit shift
  REG_TMP_CFG             = 0x07
  TMP_CFG_TMP_EXT         = 1 << 7 # Use T sensor on MEMS die instead the one on ASIC die
  TMP_CFG_TMP_RATE_1HZ    = 0 << 4
  TMP_CFG_TMP_RATE_2HZ    = 1 << 4
  TMP_CFG_TMP_RATE_4HZ    = 2 << 4
  TMP_CFG_TMP_RATE_8HZ    = 3 << 4
  TMP_CFG_TMP_RATE_16HZ   = 4 << 4 # Needs bit shift
  TMP_CFG_TMP_RATE_32HZ   = 5 << 4 # Needs bit shift
  TMP_CFG_TMP_RATE_64HZ   = 6 << 4 # Needs bit shift
  TMP_CFG_TMP_RATE_128HZ  = 7 << 4 # Needs bit shift
  # NOTE: each sample takes about 3.6 ms
  TMP_CFG_TMP_PRC_1X      = 0 << 0 # Default and might be the only one that makes sense
  TMP_CFG_TMP_PRC_2X      = 1 << 0
  TMP_CFG_TMP_PRC_4X      = 2 << 0
  TMP_CFG_TMP_PRC_8X      = 3 << 0
  TMP_CFG_TMP_PRC_16X     = 4 << 0
  TMP_CFG_TMP_PRC_32X     = 5 << 0
  TMP_CFG_TMP_PRC_64X     = 6 << 0
  TMP_CFG_TMP_PRC_128X    = 7 << 0
  REG_MEAS_CFG            = 0x08
  MEAS_CFG_COEF_RDY       = 1 << 7
  MEAS_CFG_SENSOR_RDY     = 1 << 6
  MEAS_CFG_INIT_RDY       = MEAS_CFG_COEF_RDY | MEAS_CFG_SENSOR_RDY
  MEAS_CFG_TMP_RDY        = 1 << 5
  MEAS_CFG_PRS_RDY        = 1 << 4
  MEAS_CFG_MEAS_CTRL_STBY = 0 << 0
  MEAS_CFG_MEAS_CTRL_PRS  = 1 << 0 # Single pressure measurement
  MEAS_CFG_MEAS_CTRL_TMP  = 2 << 0 # Single temperature measurement
  MEAS_CFG_MEAS_CTRL_CPRS = 5 << 0 # Continuous pressure measurement
  MEAS_CFG_MEAS_CTRL_CTMP = 6 << 0 # Continuous temperature measurement
  MEAS_CFG_MEAS_CTRL_CPT  = 7 << 0 # Continuous P+T measurement
  REG_CFG_REG             = 0x09
  CFG_REG_INT_HL          = 1 << 7
  CFG_REG_INT_FIFO        = 1 << 6
  CFG_REG_INT_TMP         = 1 << 5
  CFG_REG_INT_PRS         = 1 << 4
  CFG_REG_T_SHIFT         = 1 << 3
  CFG_REG_P_SHIFT         = 1 << 2
  CFG_REG_FIFO_EN         = 1 << 1
  CFG_REG_SPI_MODE        = 1 << 0
  REG_INT_STS             = 0x0a
  INT_STS_INT_FIFO_FULL   = 1 << 2
  INT_STS_INT_TMP         = 1 << 1
  INT_STS_INT_PRS         = 1 << 0
  REG_FIFO_STS            = 0x0b
  FIFO_STS_FIFO_FULL      = 1 << 1
  FIFO_STS_FIFO_EMPTY     = 1 << 0
  REG_RESET               = 0x0c
  RESET_FIFO_FLUSH        = 1 << 7
  RESET_SOFT_RST          = 9 << 0
  REG_PROD_ID             = 0x0d
  PROD_ID_REV_ID          = 1 << 4
  PROD_ID_PROD_ID         = 0 << 4
  PROD_ID                 = PROD_ID_REV_ID | PROD_ID_PROD_ID
  REG_COEF_C0H            = 0x10
  REG_COEF_C0L_C1H        = 0x11
  REG_COEF_C1L            = 0x12
  REG_COEF_C00H           = 0x13
  REG_COEF_C00M           = 0x14
  REG_COEF_C00L_C10H      = 0x15
  REG_COEF_C10M           = 0x16
  REG_COEF_C10L           = 0x17
  REG_COEF_C01H           = 0x18
  REG_COEF_C01L           = 0x19
  REG_COEF_C11H           = 0x1a
  REG_COEF_C11L           = 0x1b
  REG_COEF_C20H           = 0x1c
  REG_COEF_C20L           = 0x1d
  REG_COEF_C21H           = 0x1e
  REG_COEF_C21L           = 0x1f
  REG_COEF_C30H           = 0x20
  REG_COEF_C30L           = 0x21
  REG_COEF_SRCE           = 0x28
  COEF_SRCE_TMP_COEF_SRCE = 1 << 7

  # TODO: dicts of scaling factors, reg values, measurement time, and bit shift requirement for T/P
  # (currently hard-coded)

  def __init__(self, busno, address = I2C_ADDR):
    self.busno = busno
    self.bus = SMBus(busno)
    self.address = address

    self._check_id()
    self._reset()
    self._load_calibration()

  def _check_id(self):
    prod_id = self.bus.read_byte_data(self.address, self.REG_PROD_ID)
    if prod_id != self.PROD_ID:
      raise IOError('Invalid product ID 0x{:02x} (expected 0x{:02x})'.format(prod_id, self.PROD_ID))

  def _reset(self):
    self.bus.write_byte_data(self.address, self.REG_RESET, self.RESET_SOFT_RST)
    time.sleep(0.05) # Actual: 12 ms max to MEAS_CFG_SENSOR_RDY, 40 ms max to MEAS_CFG_COEF_RDY
    meas_cfg = self.bus.read_byte_data(self.address, self.REG_MEAS_CFG)
    if (meas_cfg & self.MEAS_CFG_INIT_RDY) != self.MEAS_CFG_INIT_RDY:
      raise TimeoutError('Sensor initialization timed out')
    self.bus.write_byte_data(
        self.address, self.REG_MEAS_CFG, self.MEAS_CFG_MEAS_CTRL_STBY)

  def _load_calibration(self):
    base = self.REG_COEF_C0H
    end = self.REG_COEF_C30L
    cal_data = self.bus.read_i2c_block_data(self.address, base, end - base + 1)

    '''
    s = 'CAL:'
    for byte in cal_data:
      s = '{} {:02x}'.format(s, byte)
    logi(s)
    '''

    self.c0 = (cal_data[0] << 4) | (cal_data[1] >> 4)
    self.c1 = ((cal_data[1] & 0x0f) << 8) | cal_data[2]
    self.c00 = (cal_data[3] << 12) | (cal_data[4] << 4) | (cal_data[5] >> 4)
    self.c10 = ((cal_data[5] & 0x0f) << 16) | (cal_data[6] << 8) | cal_data[7]
    self.c01 = get_word_be(cal_data, self.REG_COEF_C01H, base)
    self.c11 = get_word_be(cal_data, self.REG_COEF_C11H, base)
    self.c20 = get_word_be(cal_data, self.REG_COEF_C20H, base)
    self.c21 = get_word_be(cal_data, self.REG_COEF_C21H, base)
    self.c30 = get_word_be(cal_data, self.REG_COEF_C30H, base)

    self.c0 = twos_complement(self.c0, 12)
    self.c1 = twos_complement(self.c1, 12)
    self.c00 = twos_complement(self.c00, 20)
    self.c10 = twos_complement(self.c10, 20)
    self.c01 = twos_complement(self.c01, 16)
    self.c11 = twos_complement(self.c11, 16)
    self.c20 = twos_complement(self.c20, 16)
    self.c21 = twos_complement(self.c21, 16)
    self.c30 = twos_complement(self.c30, 16)

    self.use_mems_ts = (
        self.bus.read_byte_data(self.address, self.REG_COEF_SRCE) & self.COEF_SRCE_TMP_COEF_SRCE)
    logi(
        'Found calibration data for use with {} temperature sensor'
            .format('MEMS' if self.use_mems_ts else 'ASIC'))

  def _read_raw(self):
    # Temperature
    # Only one of the MEMS and ASIC sensors has calibration data and thus only one will be usable
    tmp_cfg = self.TMP_CFG_TMP_PRC_8X | self.TMP_CFG_TMP_RATE_1HZ
    if self.use_mems_ts:
      tmp_cfg = tmp_cfg | self.TMP_CFG_TMP_EXT
    self.bus.read_i2c_block_data(self.address, self.REG_TMP_B2, 3) # Clear status
    self.bus.write_byte_data(self.address, self.REG_TMP_CFG, tmp_cfg)
    self.bus.write_byte_data(self.address, self.REG_MEAS_CFG, self.MEAS_CFG_MEAS_CTRL_TMP)
    time.sleep(0.05) # Actual: 3.6 ms * 8 = 36.8 ms
    if not self.bus.read_byte_data(self.address, self.REG_MEAS_CFG) & self.MEAS_CFG_TMP_RDY:
      raise TimeoutError('ASIC temperature measurement timed out')
    temp = get_24bit_be(self.bus.read_i2c_block_data(self.address, self.REG_TMP_B2, 3), 0)
    temp = twos_complement(temp, 24)

    # Pressure
    prs_cfg = self.PRS_CFG_PM_PRC_64X | self.PRS_CFG_PM_RATE_1HZ
    self.bus.read_i2c_block_data(self.address, self.REG_PRS_B2, 3) # Clear status
    self.bus.write_byte_data(self.address, self.REG_PRS_CFG, prs_cfg)
    self.bus.write_byte_data(self.address, self.REG_CFG_REG, self.CFG_REG_P_SHIFT)
    self.bus.write_byte_data(self.address, self.REG_MEAS_CFG, self.MEAS_CFG_MEAS_CTRL_PRS)
    time.sleep(0.15) # Actual: 104.4 ms
    if not self.bus.read_byte_data(self.address, self.REG_MEAS_CFG) & self.MEAS_CFG_PRS_RDY:
      raise TimeoutError('Pressure measurement timed out')
    pressure = get_24bit_be(self.bus.read_i2c_block_data(self.address, self.REG_PRS_B2, 3), 0)
    pressure = twos_complement(pressure, 24)

    return temp, pressure

  def _compensate_temp(self, raw_temp):
    raw_temp_scaled = raw_temp / 7864320. # For 8X oversampling
    return self.c0 * 0.5 + self.c1 * raw_temp_scaled

  def _compensate_pressure(self, raw_pressure, raw_temp):
    raw_temp_scaled = raw_temp / 7864320. # For 8X oversampling
    raw_pressure_scaled = raw_pressure / 1040384. # For 64X oversampling
    return (
        self.c00
        + raw_pressure_scaled * (
            self.c10
            + raw_pressure_scaled * (
                self.c20
                + raw_pressure_scaled * self.c30))
        + raw_temp_scaled * self.c01
        + raw_temp_scaled * raw_pressure_scaled * (
            self.c11
            + raw_pressure_scaled * self.c21))

  def read(self):
    temp, pressure = self._read_raw()
    return self._compensate_temp(temp), self._compensate_pressure(pressure, temp)

buses     = None
addresses = []
sensors   = []

'''
Config example:

Import "envsensor.dps310"
<Module "envsensor.dps310">
  Bus         1 2 3
  Address     0x76 0x77
</Module>
'''
def config(config_in):
  global buses, addresses

  for node in config_in.children:
    key = node.key.lower()
    val = node.values
    # All config values must be integers (may come in as float type)
    for v in val:
      assert isinstance(v, (int, float))

    if key == 'bus':
      buses = val
    elif key == 'address':
      addresses = val
    else:
      logw('Skipping unknown config key "{}"'.format(key))

def init():
  global sensors, buses, addresses

  if not buses:
    buses = [1]
    logi('Buses not set, defaulting to {}'.format(str(buses)))

  for bus in buses:
    if bus is None:
      continue
    bus = round(bus)
    if not addresses:
      try:
        sensor = DPS310(bus)
        sensors.append(sensor)
        logi('Initialized sensor on i2c-{}, address 0x{:02x}'.format(bus, sensor.address))
      except:
        loge('Failed to init sensor on i2c-{} with default address'.format(bus))
    else:
      for address in addresses:
        address = round(address)
        try:
          sensor = DPS310(bus, address)
          sensors.append(sensor)
          logi('Initialized sensor on i2c-{}, address 0x{:02x}'.format(bus, address))
        except:
          loge('Failed to init sensor on i2c-{}, address 0x{:02x}'.format(bus, address))

def read(data = None):
  global sensors

  vl = collectd.Values(plugin = 'envsensor')
  for sensor in sensors:
    vl.plugin_instance = 'i2c-{}'.format(sensor.busno)
    vl.type_instance = 'DPS310_0x{:02x}'.format(sensor.address)
    try:
      temp, pressure = sensor.read()
      vl.dispatch(type = 'temperature', values = [temp])
      vl.dispatch(type = 'pressure', values = [pressure])
    except:
      loge('Failed to read sensor on i2c-{}, address 0x{:02x}'.format(sensor.busno, sensor.address))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
