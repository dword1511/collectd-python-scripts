import time

from envsensor._smbus2 import SMBus
from envsensor._utils import get_i2c_bus_number

class TSL2591:
  pass

class APDS_9250:
  '''
  Driver for Avago/Broadcom APDS-9250 RGB ambient light sensor, with lux computation.
  '''
  pass

class VEML6075:
  '''
  Driver for Vishay VEML6075 UVA and UVB sensor, with UVI (UV index) support.

  A few quirks about the sensor:
  * It has reached EOL in 2019
  * Large offset exists when without individual calibration, inaccurate in low-UV environment
  * Spectral response very sensitive to incident angle
  * UV index will be inaccurate when uncalibrated

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

  # Integration time register values in {time seconds: reg value} format.
  itime_table = {
    .05 : 0,
    .1  : 1,
    .2  : 2,
    .4  : 3,
    .8  : 4,
  }
  min_itime = min(itime_table.keys())

  # W/m2 per count @ 50 ms integration.
  # UVA has 0.93 counts per uW/cm2, UVB has 2.1 counts per uW/cm2
  UVA_TO_IRRADIANCE = 1 / 0.93 * 1.e4 / 1.e6
  UVB_TO_IRRADIANCE = 1 / 2.10 * 1.e4 / 1.e6

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
      raise IOError('Invalid chip ID (0x{:04x})'.format(device_id))

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
      raise ValueError('Invalid gain (can only be 1): ' + str(again))
    if itime not in self.itime_table.keys():
      raise ValueError(
          'Invalid integration time: '
          + str(itime)
          + ', possible values: '
          + str(self.itime_table.keys()))
    self.itime = itime
    self.uvconf = (self.itime_table[itime] << 4) | self.UV_CONF_AF

  def read_channels(self):
    if self.uvconf == None:
      raise RuntimeError('Sensor not configured')
    self.bus.write_word_data(self.address, self.CMD_UV_CONF, self.uvconf | self.UV_CONF_TRIG)

    # We need to give it some margin in addition to integration time. Datasheet gave no such values.
    # 10% + 0.1s did not work, 20% + 0.05s works for my sensor but need to give some PVT margin.
    time.sleep(self.itime * 1.25 + 0.1)

    # Read all data
    uva = self.bus.read_word_data(self.address, self.CMD_UVA_DATA)
    uvb = self.bus.read_word_data(self.address, self.CMD_UVB_DATA)
    # UVD is no longer used in latest documents
    #uvd = self.bus.read_word_data(self.address, self.CMD_UVD_DATA)
    uvd = 0
    uvcomp1 = self.bus.read_word_data(self.address, self.CMD_UVCOMP1_DATA)
    uvcomp2 = self.bus.read_word_data(self.address, self.CMD_UVCOMP2_DATA)

    # Compute saturations
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
