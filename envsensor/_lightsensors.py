import time

from envsensor._smbus2 import SMBus
from envsensor._utils import get_i2c_bus_number, uw_cm2_to_w_m2, get_word_le, get_24bit_le

class TSL2591:
  pass

class APDS_9250:
  '''
  Driver for Avago/Broadcom APDS-9250 RGB ambient light sensor, with lux computation.

  All channels are compensated internally by the sensor. Green channel is also used in ALS mode.

  Longer integration time does not make this sensor easier to saturate. Instead, the number of bits
  used increases. The measurement range stays the same and each bit represents a lower irradiance
  value.

  Measurement mode is always continuous, but changing configuration will cause the current
  measurement to be terminated and a new measurement to be started immediately.

  APDS-9250's address is always 0x52. Only 1 sensor can be on a bus unless an address translator is
  used.
  '''

  I2C_ADDR            = 0x52
  REG_MAIN_CTRL       = 0x00
  MAIN_CTRL_RESET     = 1 << 4
  MAIN_CTRL_CS_EN     = 1 << 2 # Whether to activate RGB channels instead of ALS/Green alone
  MAIN_CTRL_LS_EN     = 1 << 1 # Enable the sensor and start internal oscillator if set
  REG_LS_MEAS_RATE    = 0x04
  REG_LS_GAIN         = 0x05
  REG_PART_ID         = 0x06
  PART_ID             = 0xb2
  REG_MAIN_STATUS     = 0x07
  MAIN_STATUS_POWERON = 1 << 5
  MAIN_STATUS_LS_INT  = 1 << 4
  MAIN_STATUS_LS_DATA = 1 << 3
  REG_LS_DATA_IR_0    = 0x0a
  REG_LS_DATA_IR_1    = 0x0b
  REG_LS_DATA_IR_2    = 0x0c
  REG_LS_DATA_GREEN_0 = 0x0d
  REG_LS_DATA_GREEN_1 = 0x0e
  REG_LS_DATA_GREEN_2 = 0x0f
  REG_LS_DATA_BLUE_0  = 0x10
  REG_LS_DATA_BLUE_1  = 0x11
  REG_LS_DATA_BLUE_2  = 0x12
  REG_LS_DATA_RED_0   = 0x13
  REG_LS_DATA_RED_1   = 0x14
  REG_LS_DATA_RED_2   = 0x15
  REG_INT_CFG         = 0x19
  REG_INT_PERSISTENCE = 0x1a
  REG_LS_THRES_UP_0   = 0x21
  REG_LS_THRES_UP_1   = 0x22
  REG_LS_THRES_UP_2   = 0x23
  REG_LS_THRES_LOW_0  = 0x24
  REG_LS_THRES_LOW_1  = 0x25
  REG_LS_THRES_LOW_2  = 0x26
  REG_LS_THRES_VAR    = 0x27

  # REG_LS_GAIN values in {time seconds: reg value} format.
  again_table = {
    1 : 0,
    3 : 1,
    6 : 2,
    9 : 3,
    18: 4,
  }

  # Integration time values for REG_LS_MEAS_RATE.
  # Format: {time seconds: (reg value, max count)}.
  itime_table = {
    .4      : (0 << 4, (1 << 20) - 1),
    .2      : (1 << 4, (1 << 19) - 1),
    .1      : (2 << 4, (1 << 18) - 1),
    .05     : (3 << 4, (1 << 17) - 1),
    .025    : (4 << 4, (1 << 16) - 1),
    # No setting for 12.5 ms or 6.25 ms
    .003125 : (5 << 4, (1 << 13) - 1),
  }
  min_itime = min(itime_table.keys())

  meas_rate_table = {
    .025    : 0,
    .05     : 1,
    .1      : 2,  # Default
    .2      : 3,
    .5      : 4,
    1.      : 5,
    2.      : 6,  # Can also be 7
  }

  '''
  Response matrix: (TODO: compensation for irradiance?)
      625 nm  525 nm  465 nm  850 nm
  R   1       0.065   0.025   0.015
  G   0.255   1       0.115   0.015
  B   0.015   0.2     1       0.015
  IR  0.015   0.015   0.02    1
  '''

  # ALS (Green) channel produces 1000 counts for 59 uW/cm3 at 530 nm with 3X gain and 50 ms
  # integration time. We will be using 400 ms for maximum sensitivity.
  INT_TIME = 0.4
  ALS_TO_IRRADIANCE     = uw_cm2_to_w_m2(59. / (1000. / 3) * (0.05 / INT_TIME))
  # The following relationships are eyeballed from the relative spectral response graph
  R_TO_IRRADIANCE       = ALS_TO_IRRADIANCE / 0.96 * 0.94 # Peak
  G_TO_IRRADIANCE       = ALS_TO_IRRADIANCE
  B_TO_IRRADIANCE       = ALS_TO_IRRADIANCE / 0.96 * 0.64 # Peak
  IR_TO_IRRADIANCE      = ALS_TO_IRRADIANCE / 0.96 * 0.35 # Mean around 850 nm

  # This value can be found in the app note. Lux = LS_DATA_GREEN / (gain * integration time).
  # For incandescent light sources this is 35, for all others this is around 46.
  # Or use 40 as a catch-all.
  ALS_LUX_FACTOR_INCAN  = 35
  ALS_LUX_FACTOR_OTHERS = 46
  # A light source with IR / G greater than this ratio (in counts) should use incandescent formula
  INCAN_IRG_RATIO_THRES = 1

  # CCT (Correlated Color Temperature) coefficients:
  CCT_COEFF = (
    (-0.067849073, 0.708704342, -0.50282272),
    (-0.151549294, 0.714781775, -0.340903875),
    (-0.306018955, 0.338182367,  0.476947762),
  )

  # Channel modes. We only have one configuration register so only a single group.
  # We always use 400 ms integration time for maximum sensitivity.
  channel_modes = [{
    'channels': {
      'R'   : True,
      'G'   : True,
      'B'   : True,
      'IR'  : True,
      'lux' : False,
      'CCT' : False,
    },
    'gain_table': {
      1 : (1 , INT_TIME),
      3 : (3 , INT_TIME),
      6 : (6 , INT_TIME),
      9 : (9 , INT_TIME),
      18: (18, INT_TIME),
    }
  }]

  def __init__(self, bus, address = I2C_ADDR):
    self.bus = SMBus(get_i2c_bus_number(bus))
    self.address = address

    # Verify chip ID
    device_id = self.bus.read_byte_data(self.address, self.REG_PART_ID)
    if device_id != self.PART_ID:
      raise IOError('Invalid part ID (0x{:04x})'.format(device_id))

    # Reset and enable the sensor
    try:
      self.bus.write_byte_data(self.address, self.REG_MAIN_CTRL, self.MAIN_CTRL_RESET)
    except OSError:
      # It literrally resets before it could ACK?
      pass
    time.sleep(0.01)
    self.bus.write_byte_data(
        self.address, self.REG_MAIN_CTRL, self.MAIN_CTRL_CS_EN | self.MAIN_CTRL_LS_EN)
    time.sleep(0.01)

  def get_channel_modes(self):
    return self.channel_modes

  def set_channel_mode(self, name, again, itime):
    if name not in self.channel_modes[0]['channels'].keys():
      raise KeyError('Invalid channel: ' + name)
    if again not in self.again_table.keys():
      raise ValueError(
          'Invalid analog gain: '
          + str(again)
          + ', possible values: '
          + str(self.again_table.keys()))
    if itime != self.INT_TIME:
      raise ValueError('Invalid integration time (can only be {}): {}'.format(INT_TIME, itime))

    self.again = again
    self.bus.write_byte_data(self.address, self.REG_LS_GAIN, self.again_table[again])

  def read_channels(self):
    # Invalidate old data
    self.bus.read_byte_data(self.address, self.REG_LS_DATA_GREEN_0)
    # Setting REG_LS_MEAS_RATE to trigger measurement immediately.
    # Use lowest rate to avoid unnecessary measurements.
    self.bus.write_byte_data(
        self.address,
        self.REG_LS_MEAS_RATE,
        self.itime_table[self.INT_TIME][0] | self.meas_rate_table[2.])

    # Wait for result (ADC conversion takes an additional 3.28 ms max)
    time.sleep(self.INT_TIME * 1.1 + 0.004)
    if not self.bus.read_byte_data(self.address, self.REG_MAIN_STATUS) & self.MAIN_STATUS_LS_DATA:
      raise TimeoutError('Sensor measurement timeout')

    # Read measurement data
    base = self.REG_LS_DATA_IR_0
    length = self.REG_LS_DATA_RED_2 - self.REG_LS_DATA_IR_0 + 1
    data = self.bus.read_i2c_block_data(self.address, base, length)
    r_count = get_24bit_le(data, self.REG_LS_DATA_RED_0, base)
    g_count = get_24bit_le(data, self.REG_LS_DATA_GREEN_0, base)
    b_count = get_24bit_le(data, self.REG_LS_DATA_BLUE_0, base)
    ir_count = get_24bit_le(data, self.REG_LS_DATA_IR_0, base)

    # Compute saturation
    max_count = self.itime_table[self.INT_TIME][1] + 1
    sat_r = (r_count + 1) / max_count
    sat_g = (g_count + 1) / max_count
    sat_b = (b_count + 1) / max_count
    sat_ir = (ir_count + 1) / max_count
    sat_p = max([sat_r, sat_g, sat_b, sat_ir])

    # Compute radiometric channels
    r = r_count * self.R_TO_IRRADIANCE / self.again
    g = g_count * self.G_TO_IRRADIANCE / self.again
    b = b_count * self.B_TO_IRRADIANCE / self.again
    ir = ir_count * self.IR_TO_IRRADIANCE / self.again

    # Compute illuminance
    incan_ratio = min(float(ir_count) / g_count, 1.)
    lux_incan = g_count / (self.INT_TIME * 1000 * self.again) * self.ALS_LUX_FACTOR_INCAN
    lux_others = g_count / (self.INT_TIME * 1000 * self.again) * self.ALS_LUX_FACTOR_OTHERS
    lux = incan_ratio * lux_incan + (1. - incan_ratio) * lux_others

    # Compute CCT
    cie_coeff = self.CCT_COEFF[0]
    cie_x = cie_coeff[0] * r_count + cie_coeff[1] * g_count + cie_coeff[2] * b_count
    cie_coeff = self.CCT_COEFF[1]
    cie_y = cie_coeff[0] * r_count + cie_coeff[1] * g_count + cie_coeff[2] * b_count
    cie_coeff = self.CCT_COEFF[2]
    cie_z = cie_coeff[0] * r_count + cie_coeff[1] * g_count + cie_coeff[2] * b_count
    cct_x = cie_x / (cie_x + cie_y + cie_z)
    cct_y = cie_y / (cie_x + cie_y + cie_z)
    cct_n = (cct_x - 0.3320) / (0.1858 - cct_y)
    cct = 449 * (cct_n ** 3) + 3525 * (cct_n ** 2) + 6823.3 * cct_n + 5520.33

    return {
      'R' : {
        'value'     : r,
        'saturation': sat_r,
        'again'     : self.again,
        'itime'     : self.INT_TIME,
      },
      'G' : {
        'value'     : g,
        'saturation': sat_g,
        'again'     : self.again,
        'itime'     : self.INT_TIME,
      },
      'B' : {
        'value'     : b,
        'saturation': sat_b,
        'again'     : self.again,
        'itime'     : self.INT_TIME,
      },
      'IR' : {
        'value'     : ir,
        'saturation': sat_ir,
        'again'     : self.again,
        'itime'     : self.INT_TIME,
      },
      'lux' : {
        'value'     : lux,
        'saturation': sat_p,
        'again'     : self.again,
        'itime'     : self.INT_TIME,
      },
      'CCT' : {
        'value'     : cct,
        'saturation': sat_p,
        'again'     : self.again,
        'itime'     : self.INT_TIME,
      },
    }

class VEML6075:
  '''
  Driver for Vishay VEML6075 UVA and UVB sensor, with UVI (UV index) support.

  A few quirks about the sensor:
  * It has reached EOL in 2019
  * Large offset exists when without individual calibration, inaccurate in low-UV environment
  * Spectral response very sensitive to incident angle
  * UV index will be inaccurate when uncalibrated
  * There is no way to know whether measurement has been completed or not
  * I2C access is word-based and there is no possibility for block read

  VEML6075's address is always 0x10. Only 1 sensor can be on a bus unless an address translator is
  used.
  '''

  I2C_ADDR          = 0x10
  CMD_UV_CONF       = 0x00
  UV_CONF_SD        = 1 << 0
  UV_CONF_AF        = 1 << 1
  UV_CONF_TRIG      = 1 << 2
  UV_CONF_HD        = 1 << 3 # None of their doc explained what exactly is this
  CMD_UVA_DATA      = 0x07
  CMD_UVD_DATA      = 0x08 # Dummy channel for dark-current cancellation, later removed in app note
  CMD_UVB_DATA      = 0x09
  CMD_UVCOMP1_DATA  = 0x0a # Visible light compensation channel
  CMD_UVCOMP2_DATA  = 0x0b # Near IR compensation channel
  CMD_ID            = 0x0c
  DEVICE_ID         = 0x0026

  # Integration time values for CMD_UV_CONF in {time seconds: reg value} format.
  itime_table = {
    .05 : 0 << 4,
    .1  : 1 << 4,
    .2  : 2 << 4,
    .4  : 3 << 4,
    .8  : 4 << 4,
  }
  min_itime = min(itime_table.keys())

  # W/m2 per count @ 50 ms integration.
  # UVA has 0.93 counts per uW/cm2, UVB has 2.1 counts per uW/cm2
  UVA_TO_IRRADIANCE = uw_cm2_to_w_m2(1 / 0.93 * 1.e4 / 1.e6)
  UVB_TO_IRRADIANCE = uw_cm2_to_w_m2(1 / 2.10 * 1.e4 / 1.e6)

  # Data for compensation and UVI calculation.
  # These data are in the app note but not the datasheet.
  # Document 84339 revision 25-Apr-2018, using values for open-air systems.
  # These parameters can be calibrated against a UV meter with 2 different light sources.
  UVA_A_COEF        = 2.22
  UVA_B_COEF        = 1.33
  UVB_C_COEF        = 2.95
  UVB_D_COEF        = 1.74
  UVA_UVI_RESPONSE  = 0.001461
  UVB_UVI_RESPONSE  = 0.002591

  # Channel modes. We only have one configuration register so only a single group.
  channel_modes = [{
    'channels': {
      'UVA' : True,
      'UVB' : True,
      'UVI' : False,
    },
    'gain_table': {
      1 : (1, 0.05),
      2 : (1, 0.1 ),
      4 : (1, 0.2 ),
      8 : (1, 0.4 ),
      16: (1, 0.8 ),
    }
  }]

  def __init__(self, bus, address = I2C_ADDR):
    self.bus = SMBus(get_i2c_bus_number(bus))
    self.address = address

    # Verify chip ID
    device_id = self.bus.read_word_data(self.address, self.CMD_ID)
    if device_id != self.DEVICE_ID:
      raise IOError('Invalid device ID (0x{:04x})'.format(device_id))

    # Power cycle and set single measurement mode
    self.bus.write_word_data(self.address, self.CMD_UV_CONF, self.UV_CONF_SD)
    time.sleep(0.01)
    self.bus.write_word_data(self.address, self.CMD_UV_CONF, self.UV_CONF_AF)
    time.sleep(0.01)
    self.uvconf = None

  def get_channel_modes(self):
    return self.channel_modes

  def set_channel_mode(self, name, again, itime):
    if name not in self.channel_modes[0]['channels'].keys():
      raise KeyError('Invalid channel: ' + name)
    if again != 1:
      raise ValueError('Invalid analog gain (can only be 1): ' + str(again))
    if itime not in self.itime_table.keys():
      raise ValueError(
          'Invalid integration time: '
          + str(itime)
          + ', possible values: '
          + str(self.itime_table.keys()))

    self.itime = itime
    self.uvconf = self.itime_table[itime] | self.UV_CONF_AF

  def read_channels(self):
    if self.uvconf == None:
      raise RuntimeError('Sensor not configured')
    self.bus.write_word_data(self.address, self.CMD_UV_CONF, self.uvconf | self.UV_CONF_TRIG)

    # We need to give it some margin in addition to integration time.
    # Datasheet gave no such values, and there is no status register to check.
    # 10% + 0.1s did not work, 20% + 0.05s works for my sensor but need to give some PVT margin.
    time.sleep(self.itime * 1.25 + 0.1)

    # Read all data
    # NOTE: this sensor does not support block read (each address hosts 16 bits of data)
    uva = self.bus.read_word_data(self.address, self.CMD_UVA_DATA)
    uvb = self.bus.read_word_data(self.address, self.CMD_UVB_DATA)
    # UVD is no longer used in latest documents
    #uvd = self.bus.read_word_data(self.address, self.CMD_UVD_DATA)
    uvd = 0
    uvcomp1 = self.bus.read_word_data(self.address, self.CMD_UVCOMP1_DATA)
    uvcomp2 = self.bus.read_word_data(self.address, self.CMD_UVCOMP2_DATA)

    # Compute saturation values
    uva_sat = (uva + 1) / (1 << 16)
    uvb_sat = (uvb + 1) / (1 << 16)
    uvd_sat = (uvd + 1) / (1 << 16)
    uvcomp1_sat = (uvcomp1 + 1) / (1 << 16)
    uvcomp2_sat = (uvcomp2 + 1) / (1 << 16)
    uva_sat = max([uva_sat, uvd_sat, uvcomp1_sat, uvcomp2_sat])
    uvb_sat = max([uvb_sat, uvd_sat, uvcomp1_sat, uvcomp2_sat])

    # Correct for dark current
    uva -= uvd
    uvb -= uvd
    uvcomp1 -= uvd
    uvcomp2 -= uvd

    # Spectral response compensation
    uva -= self.UVA_A_COEF * uvcomp1 + self.UVA_B_COEF * uvcomp2
    uvb -= self.UVB_C_COEF * uvcomp1 + self.UVB_D_COEF * uvcomp2
    uva = max(uva, 0)
    uvb = max(uvb, 0)
    uvi = (uva * self.UVA_UVI_RESPONSE + uvb * self.UVB_UVI_RESPONSE) / 2
    uvi = min(12, max(0, uvi)) # UVI must be in [0, 12]

    # Take integration time into consideration
    reponse_uva = self.UVA_TO_IRRADIANCE / (self.itime / self.min_itime)
    reponse_uvb = self.UVB_TO_IRRADIANCE / (self.itime / self.min_itime)
    return {
      'UVA' : {
        'value'     : uva * reponse_uva,
        'saturation': uva_sat,
        'again'     : 1,
        'itime'     : self.itime,
      },
      'UVB' : {
        'value'     : uvb * reponse_uvb,
        'saturation': uvb_sat,
        'again'     : 1,
        'itime'     : self.itime,
      },
      'UVI' : {
        'value'     : uvi,
        'saturation': max([uva_sat, uvb_sat]),
        'again'     : 1,
        'itime'     : self.itime,
      },
    }
