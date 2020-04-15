#!/usr/bin/env python

# A few quirks about the sensor:
# * It has reached EOL in 2019
# * Large offset exists when without individual calibration, inaccurate in low-UV environment
# * Spectral response very sensitive to incident angle
# * UV index will be inaccurate when uncalibrated

import time
import traceback as tb

import collectd
from envsensor._smbus2 import SMBus

class VEML6075:
  # NOTE: VEML6075's address is always 0x10. Only 1 sensor can be on a bus unless an address translator is used.
  I2C_ADDR          = 0x10
  CMD_UV_CONF       = 0x00
  CMD_UVA_DATA      = 0x07
  CMD_UVD_DATA      = 0x08 # dummy channel for dark-current cancellation, later removed in app note
  CMD_UVB_DATA      = 0x09
  CMD_UVCOMP1_DATA  = 0x0a
  CMD_UVCOMP2_DATA  = 0x0b
  CMD_ID            = 0x0c
  DEVICE_ID         = 0x0026

  # {time millis: (reg value, gain)}
  integration_table = {
    50  : (0,  1),
    100 : (1,  2),
    200 : (2,  4),
    400 : (3,  8),
    800 : (4, 16),
  }

  # uW/cm2 per count @ 50 ms integration
  RESPONSE_UVA      = 1 / 0.93
  RESPONSE_UVB      = 1 / 2.10
  # These data are in the app note but not the datasheet
  # Document 84339 revision 25-Apr-2018, for open-air systems
  # These parameters can be calibrated against a UV meter with 2 different light sources
  UVA_A_COEF        = 2.22
  UVA_B_COEF        = 1.33
  UVB_C_COEF        = 2.95
  UVB_D_COEF        = 1.74
  UVA_UVI_RESPONSE  = 0.001461
  UVB_UVI_RESPONSE  = 0.002591
  # AGC settings
  LOWEST_IT_MILLIS  = min(integration_table.keys())
  GAIN_MARGIN       = 0.5               # Allow 50% error in gain
  MAX_COUNT         = (1 << 16) * 0.95  # Avoid top 95% for linearity's sake

  def __init__(self, busno = 1, address = I2C_ADDR):
    self.busno = busno
    self.bus = SMBus(busno)
    self.address = address
    chip_id = self.bus.read_word_data(self.address, self.CMD_ID)
    if chip_id != self.DEVICE_ID:
      raise IOError('Invalid chip ID (0x{:04x})'.format(chip_id))
    # Power cycle and set single measurement mode
    self.bus.write_word_data(self.address, self.CMD_UV_CONF, 1 << 0) # power off
    time.sleep(0.01)
    self.bus.write_word_data(self.address, self.CMD_UV_CONF, 1 << 1) # power on, active force mode
    time.sleep(0.01)

  def get_uv(self):
    # Estimate with lowest gain
    next_it_millis = self.LOWEST_IT_MILLIS
    uva_est, uvb_est, uvi_est, max_count = self._read_compensated_uv(next_it_millis)

    # Read with higher precision
    gain = (1 << 16) / (max_count + 1) / (1 + self.GAIN_MARGIN)
    for it_millis in self.integration_table.keys():
      if self.integration_table[it_millis][1] <= gain and it_millis > next_it_millis:
        next_it_millis = it_millis
    uva, uvb, uvi, max_count = self._read_compensated_uv(next_it_millis)

    overflown = max_count > self.MAX_COUNT
    if overflown:
      uva = uva_est
      uvb = uvb_est
      uvi = uvi_est
      next_it_millis = self.LOWEST_IT_MILLIS
    return uva, uvb, uvi, overflown, next_it_millis

  def _read_compensated_uv(self, integration_millis):
    self.bus.write_word_data(
        self.address,
        self.CMD_UV_CONF,
        (self.integration_table[integration_millis][0] << 4) | (1 << 2) | (1 << 1))
    # We need to give it some margin in addition to integration time. Datasheet gave no such value
    # (1.1X + 100 did not work! 1.2X + 50 works on my sensor but need to give a bit extra for PVT)
    time.sleep((integration_millis * 1.25 + 100) / 1000)
    # Take integration time into consideration
    reponse_uva = self.RESPONSE_UVA / self.integration_table[integration_millis][1]
    reponse_uvb = self.RESPONSE_UVB / self.integration_table[integration_millis][1]

    #uvd = self.bus.read_word_data(self.address, self.CMD_UVD_DATA)
    uva = self.bus.read_word_data(self.address, self.CMD_UVA_DATA)
    uvb = self.bus.read_word_data(self.address, self.CMD_UVB_DATA)
    uvcomp1 = self.bus.read_word_data(self.address, self.CMD_UVCOMP1_DATA)
    uvcomp2 = self.bus.read_word_data(self.address, self.CMD_UVCOMP2_DATA)

    '''
    collectd.debug(
        'uva {} uvb {} uvd {} uvcomp1 {} uvcomp2 {}'.format(uva, uvb, uvd, uvcomp1, uvcomp2))
    '''

    max_count = max([uva, uvb, uvcomp1, uvcomp2])
    '''
    uva -= uvd
    uvb -= uvd
    uvcomp1 -= uvd
    uvcomp2 -= uvd
    '''
    uva -= self.UVA_A_COEF * uvcomp1 + self.UVA_B_COEF * uvcomp2
    uvb -= self.UVB_C_COEF * uvcomp1 + self.UVB_D_COEF * uvcomp2
    uva = max(uva, 0)
    uvb = max(uvb, 0)
    uvi = (uva * self.UVA_UVI_RESPONSE + uvb * self.UVB_UVI_RESPONSE) / 2
    uvi = min(12, max(0, uvi)) # UVI must be in [0, 12]
    return uva * reponse_uva, uvb * reponse_uvb, uvi, max_count

buses   = []
sensors = []

'''
Config example:

Import "envsensor.veml6075"
<Module "envsensor.veml6075">
  Buses       "1 2 3 5 7"
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
    else:
      collectd.warning('{}: Skipping unknown config key {}'.format(__name__, node.key))

def init():
  global sensors, buses

  if not buses:
    buses = [1]
    collectd.info('{}: Buses not set, defaulting to {}'.format(__name__, str(buses)))

  for bus in buses:
    if bus is None:
      continue
    try:
      sensor = VEML6075(bus)
      sensors.append(sensor)
      collectd.info(
          '{}: Initialized sensor on i2c-{}'.format(__name__, bus,))
    except:
      collectd.error(
          '{}: Failed to init sensor on i2c-{}: {}'.format(__name__, bus, tb.format_exc()))

def read(data = None):
  global sensors

  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'

  for sensor in sensors:
    try:
      uva, uvb, uvi, overflown, it_millis = sensor.get_uv()
      wm2_per_uwcm2 = 1.e4 / 1.e6
      if overflown:
        collectd.warning(
            '{}: sensor on i2c-{} fallback to lowest gain, unstable light?'
                .format(__name__, sensor.busno))
      vl.dispatch(
          type = 'count',
          plugin_instance = 'i2c-{}_W-m2'.format(sensor.busno),
          type_instance = 'VEML6075_UVA',
          values = [uva * wm2_per_uwcm2])
      vl.dispatch(
          type = 'count',
          plugin_instance = 'i2c-{}_W-m2'.format(sensor.busno),
          type_instance = 'VEML6075_UVB',
          values = [uvb * wm2_per_uwcm2])
      vl.dispatch(
          type = 'gauge',
          plugin_instance = 'i2c-{}_UVI'.format(sensor.busno),
          type_instance = 'VEML6075',
          values = [uvi])
      vl.dispatch(
          type = 'gauge',
          plugin_instance = 'i2c-{}_itime'.format(sensor.busno),
          type_instance = 'VEML6075',
          values = [it_millis * 1.e-3])
    except:
      collectd.error(
          '{}: Failed to read sensor on i2c-{}: {}'
              .format(__name__, sensor.busno, tb.format_exc()))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
