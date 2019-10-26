#!/usr/bin/env python

# Depends on: python-tsl2591

# NOTE: TSL2591x's address is always 0x29. Only 1 sensor can be on a bus unless an address translator is used.
# Known bugs: cannot be used with other scripts that access the same sensor -- sensor settings will become incoherent!


import sys, traceback

import collectd
from _tsl2591 import TSL2591


GAIN_MARGIN = 0.5 # Allow 50% error in gain
MAX_RETRIES = 3   # Try to find optimal setting in 3 trials

sensors           = []
buses             = []
report_lux        = True
report_multiplier = False


'''
Config example:

Import "envsensor.tsl2591"
<Module "envsensor.tsl2591">
  Buses       "1 2 3 5 7"
  Lux         false
  Multiplier  true
</Module>
'''
def do_config(config_in):
  global sensors, buses, report_lux, report_multiplier

  buses_set = False

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
      buses_set = True

    elif key == 'lux':
      if type(val) is type(False):
        report_lux = val
      else:
        collectd.error('{}: "{}" for {} is not bool, skipping'.format(__name__, node.values[0], node.key))

    elif key == 'multiplier':
      if type(val) is type(False):
        report_multiplier = val
      else:
        collectd.error('{}: "{}" for {} is not bool, skipping'.format(__name__, node.values[0], node.key))

    else:
      collectd.warning('{}: Skipping unknown config key {}'.format(__name__, node.key))

  if not buses_set:
    buses = [1]
    collectd.info('{}: Buses not set, defaulting to [1]'.format(__name__))


def do_init():
  global sensors, buses

  collectd.debug('buses = ' + str(buses))
  for bus in buses:
    if bus is None:
      continue
    try:
      sensor = TSL2591(bus)
      sensor.enable()
      sensors.append(sensor)
      collectd.info('{}: Initialized sensor on i2c-{}'.format(__name__, bus))
    except:
      etype, value, trace = sys.exc_info()
      tb = ['Traceback (most recent call last):\n']
      tb = tb + traceback.format_exception(etype, value, trace)
      collectd.error('{}: Failed to init sensor:\n{}'.format(__name__, str(tb)))


'''
Call like:
_dispatch(collectd.Values(), **sensor.get_all())
sensor.get_all() returns a dict containing full, ir, lux, gain, integration_time, multiplier, bus
'''
def _dispatch(vl, bus, lux, full, ir, multiplier, **_):
  global report_lux, report_multiplier

  s_instance = 'i2c-{}_TSL2591'.format(bus)

  # NOTE: rrdtool has the '-o' option for logarithmic plotting
  # NOTE: type such as signal_power, snr has limited range and won't work

  vl.plugin_instance = s_instance + '_RAW'
  try:
    vl.dispatch(type = 'count', type_instance = 'IR', values = [float(ir) / multiplier])
  except:
    collectd.error('{}: Failed to dispatch RAW: {}'.format(__name__, str(sys.exc_info())))
  try:
    vl.dispatch(type = 'count', type_instance = 'Full', values = [float(full) / multiplier])
  except:
    collectd.error('{}: Failed to dispatch RAW: {}'.format(__name__, str(sys.exc_info())))

  if report_lux and (lux is not None):
    vl.plugin_instance = s_instance + '_Lux'
    try:
      vl.dispatch(type = 'gauge', values = [max(lux, 0)])
      if (lux < 0):
        collectd.warning('{}: Sensor on i2c-{} reported invalid Lux value "{}"'.format(__name__, bus, lux))
    except:
      collectd.error('{}: Failed to dispatch Lux: {}'.format(__name__, str(sys.exc_info())))

  # Mostly debugging
  if report_multiplier:
    vl.plugin_instance = s_instance + '_Multiplier'
    try:
      vl.dispatch(type = 'gauge', values = [multiplier])
    except:
      collectd.error('{}: Failed to dispatch Multiplier: {}'.format(__name__, str(sys.exc_info())))


def _read_iteration(sensor):
  m_curr = sensor.get_multiplier()
  est_result = sensor.get_all()

  est_full = max(1, est_result['full'])
  # NOTE: if we ever need to go for higher gain, we will have at least 200 ms integration_time, so max_count is always 65535
  #additional_multiplier = float(sensor.get_max_count() / est_full)
  additional_multiplier = 65535. / est_full
  collectd.debug('Full = {}, additional multiplier needed = {}'.format(est_full, additional_multiplier))

  total_multiplier = additional_multiplier * m_curr
  sensor.set_multiplier(total_multiplier / (1. + GAIN_MARGIN)) # selects and changes sensor setting
  actual_multiplier = sensor.get_multiplier()
  collectd.debug('Asked for multiplier {}, got {} -> {}'.format(total_multiplier, m_curr, actual_multiplier))

  if actual_multiplier == m_curr:
    # Current setting is good
    return True, est_result
  elif actual_multiplier < m_curr:
    # Might be unstable lighting, play safe
    collectd.warning('{}: Unstable light for sensor on i2c-{}?'.format(__name__, sensor.get_bus_no()))
    return True, est_result
  else:
    return False, est_result


def _read_sensor(sensor, vl):
  # Try lowest gain first
  sensor.set_gain(TSL2591.GAIN_LOW)
  sensor.set_timing(TSL2591.INTEGRATIONTIME_100MS)

  converged = False
  full = 0
  ir = 0
  multiplier = 0
  for _ in range(0, MAX_RETRIES):
    converged, results = _read_iteration(sensor)
    if converged:
      # NOTE: usually, the FULL sensor should saturate before the IR sensor
      if results['lux'] is None:
        collectd.warning('{}: Sensor on i2c-{} have saturated: full = {}, ir = {}, lux = {}'.format(__name__, results['bus'], results['full'], results['ir'], results['lux']))
      _dispatch(vl, **results)
      return

  collectd.warning('{}: Could not optimize gain/time settings within {} iterations'.format(__name__, MAX_RETRIES))
  _dispatch(vl, **results)


def do_read(data = None):
  global sensors

  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'

  for sensor in sensors:
    _read_sensor(sensor, vl)


collectd.register_config(do_config)
collectd.register_init(do_init)
collectd.register_read(do_read)
