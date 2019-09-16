#!/usr/bin/env python

# Depends on: python-tsl2591

# TODO: config for bus number, multi-sensor (enumerate)
# TODO: keep sensor as a global variable
# TODO: Lux calculation from library does not work under low light conditions
# Known bugs: cannot be used with other scripts that access the same sensor -- sensor settings will become incoherent!

import collectd
from python_tsl2591 import *

GAIN_X_MED  = 25
GAIN_X_HIGH = 428
GAIN_X_MAX  = 9876

# Allow 20% error in gain
GAIN_MARGIN = 0.2

MULTIPLIER_MAX = 9876 * 6
MAX_RETRIES = 3

def dispatch(vl, full, ir, lux, multiplier = 1):
  # TODO: dB instead of linear RAW value?
  # NOTE: Lux could be negative if the FULL sensor is saturated

  # NOTE: usually, the FULL sensor should saturate before the IR sensor
  if ir >= 37888 or full >= 37888:
    collectd.warning('TSL2591 have saturated: full = {}, ir = {}, lux = {}'.format(full, ir, lux))

  vl.plugin_instance = 'TSL2591_RAW'
  try:
    vl.dispatch(type = 'gauge', type_instance = 'IR', values = [float(ir) / multiplier])
  except:
    pass
  try:
    vl.dispatch(type = 'gauge', type_instance = 'Full', values = [float(full) / multiplier])
  except:
    pass

  vl.plugin_instance = 'TSL2591_Lux'
  try:
    if (lux >= 0):
      vl.dispatch(type = 'gauge', values = [lux])
    elif (lux > -1):
      # Tolerate small error
      vl.dispatch(type = 'gauge', values = [0])
  except:
    pass

  # Mostly debugging
  vl.plugin_instance = 'TSL2591_Multiplier'
  try:
    vl.dispatch(type = 'gauge', values = [multiplier])
  except:
    pass

def get_multiplier(sensor):
  gain_to_multiplier = {
    GAIN_LOW : 1,
    GAIN_MED : GAIN_X_MED,
    GAIN_HIGH: GAIN_X_HIGH,
    GAIN_MAX : GAIN_X_MAX,
  }
  atime_to_multiplier = {
    INTEGRATIONTIME_100MS: 1.,
    INTEGRATIONTIME_200MS: 2.,
    INTEGRATIONTIME_300MS: 3.,
    INTEGRATIONTIME_400MS: 4.,
    INTEGRATIONTIME_500MS: 5.,
    INTEGRATIONTIME_600MS: 6.,
  }

  m_gain  = gain_to_multiplier[sensor.get_gain()]
  m_atime = atime_to_multiplier[sensor.get_timing()]

  collectd.debug('Multiplier: Gain = {}, ATIME = {}, total = {}'.format(m_gain, m_atime, m_gain * m_atime))
  return m_gain * m_atime

def refine_setting_by_multiplier(multiplier, sensor):
  # Determine ATIME
  # TODO: dict + loop, maybe
  if multiplier > 6 * (1 + GAIN_MARGIN):
    sensor.set_timing(INTEGRATIONTIME_600MS)
    multiplier = multiplier / 6
  elif multiplier > 5 * (1 + GAIN_MARGIN):
    sensor.set_timing(INTEGRATIONTIME_500MS)
    multiplier = multiplier / 5
  elif multiplier > 4 * (1 + GAIN_MARGIN):
    sensor.set_timing(INTEGRATIONTIME_400MS)
    multiplier = multiplier / 4
  elif multiplier > 3 * (1 + GAIN_MARGIN):
    sensor.set_timing(INTEGRATIONTIME_300MS)
    multiplier = multiplier / 3
  elif multiplier > 2 * (1 + GAIN_MARGIN):
    sensor.set_timing(INTEGRATIONTIME_200MS)
    multiplier = multiplier / 2

  # Determine analog gain
  if multiplier > GAIN_X_MAX * (1 + GAIN_MARGIN):
    sensor.set_gain(GAIN_MAX)
    multiplier = multiplier / GAIN_X_MAX
  elif multiplier > GAIN_X_HIGH * (1 + GAIN_MARGIN):
    sensor.set_gain(GAIN_HIGH)
    multiplier = multiplier / GAIN_X_HIGH
  elif multiplier > GAIN_X_MED * (1 + GAIN_MARGIN):
    sensor.set_gain(GAIN_MED)
    multiplier = multiplier / GAIN_X_MED

  collectd.debug('Unmet multiplier = {}'.format(multiplier))

def read_iteration(sensor):
  settled = False
  m_curr = get_multiplier(sensor)
  est_full, est_ir = sensor.get_full_luminosity()

  est_full_div = est_full
  if est_full_div < 1:
    est_full_div = 1
  additional_multiplier = float(37888 / est_full_div)
  collectd.debug('Full = {}, additional multiplier needed = {}'.format(est_full, additional_multiplier))

  total_multiplier = additional_multiplier * m_curr
  refine_setting_by_multiplier(total_multiplier, sensor)
  if get_multiplier(sensor) <= m_curr:
    # Current setting is good
    # TODO: unnecessary I2C communication
    return True, est_full, est_ir, m_curr
  else:
    return False, est_full, est_ir, m_curr

def read(data = None):
  sensor = tsl2591(1)
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'

  # Try lowest gain first
  sensor.set_gain(GAIN_LOW)
  sensor.set_timing(INTEGRATIONTIME_100MS)

  converged = False
  full = 0
  ir = 0
  multiplier = 0
  for _ in range(0, MAX_RETRIES):
    converged, full, ir, multiplier = read_iteration(sensor)
    if converged:
      sensor.bus.close() # Bugfix for tsl2591
      dispatch(vl, full, ir, sensor.calculate_lux(full, ir), multiplier)
      return

  collectd.warning('Could not optimize gain/time settings within {} iterations'.format(MAX_RETRIES))
  sensor.bus.close() # Bugfix for tsl2591
  dispatch(vl, full, ir, sensor.calculate_lux(full, ir), multiplier)

collectd.register_read(read)
