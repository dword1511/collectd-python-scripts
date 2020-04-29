'''
Generic magnetometer plugin.

This plugin tracks magnetic field strength rather than compass direction.
'''

import math

import collectd

from envsensor._utils import MultiInstanceCollectdPlugin
import envsensor._magnetometers as magnetometers

class Instance:
  '''
  Handles an instance of plugin on a particular bus with a specified driver.

  Will throw an exception if initialization fails.

  The driver needs to implement the following functions:
  * __init__(bus, address = None): create a sensor object on the bus specified by string in the bus
        parameter, optionally with an address. If no address is supplied, the default shall be used.
        Each sensor may have multiple channels (e.g. X, Y, Z, and temperature).
  * read_channels(): triggers one measurement on all channels, and returns the results.
        This function shall block during the measurement. The returned results should have the
        following structure:
          {
            'name': {
              'value': float-point value converted to appropriate units (micro-Tesla, Celsius, etc.)
              'type': 'magnetic', 'thermal', etc.
            },
            ...
          }
        The magnetic channels should be in micro Teslas, while the thermal channels should be in
        degrees Celsius.
  '''

  def __init__(self, config, bus):
    # NOTE: the same config will be used by multiple instances, so do not modify and do not use
    # config['bus']
    if 'Address' in config.keys():
      self.sensor = config['Driver'](bus = bus, address = config['Address'])
    else:
      self.sensor = config['Driver'](bus = bus)
    self.config = config
    self.bus = bus
    self.driver_name = config['Driver'].__name__

    self.baseline = Instance.get_channels_by_type(self.sensor.read_channels(), 'magnetic')
    if config['LogEuclidean']:
      self.baseline['Euclidean'] = Instance.get_euclidean(self.baseline)
    if config['LogDelta']:
      self.delta_baseline = self.baseline.copy()

  def get_channels_by_type(measurement, type_str):
    return {name: data['value'] for name, data in measurement.items() if data['type'] == type_str}

  def get_euclidean(channels):
    return math.sqrt(sum([value ** 2 for _, value in channels.items()]))

  def dispatch(self, vl):
    measurement = self.sensor.read_channels()
    magnetic_channels = Instance.get_channels_by_type(measurement, 'magnetic')
    thermal_channels = Instance.get_channels_by_type(measurement, 'thermal')
    if self.config['LogEuclidean']:
      magnetic_channels['Euclidean'] = Instance.get_euclidean(magnetic_channels)

    if self.config['LogInstant']:
      alpha = self.config['Alpha']
      for name, value in magnetic_channels.items():
        if name == 'Euclidean' and not self.config['LogEuclidean']:
          continue
        if name != 'Euclidean' and not self.config['LogAxes']:
          continue
        value = self.baseline[name] * (1 - alpha) + value * alpha
        self.baseline[name] = value
        vl.dispatch(
            type = 'gauge',
            plugin_instance = self.bus + '_uT',
            type_instance = self.driver_name + '_' + name,
            values = [value])

    if self.config['LogDelta']:
      alpha = self.config['DeltaAlpha']
      for name, value in magnetic_channels.items():
        if name == 'Euclidean' and not self.config['LogEuclidean']:
          continue
        if name != 'Euclidean' and not self.config['LogAxes']:
          continue
        delta = value - self.delta_baseline[name]
        self.delta_baseline[name] = self.delta_baseline[name] * (1 - alpha) + value * alpha
        vl.dispatch(
            type = 'gauge',
            plugin_instance = self.bus + '_uT-delta',
            type_instance = self.driver_name + '_' + name,
            values = [delta])

    if self.config['LogTemperature']:
      for name, value in thermal_channels.items():
        vl.dispatch(
            type = 'temperature',
            plugin_instance = self.bus,
            type_instance = self.driver_name + '_' + name,
            values = [value])

'''
Example config block:
<Module "envsensor.magnetometer">
  Driver              "HMC5883L"    # Mandatory, see _lightsensors.py for possible values.
  Bus                 "i2c-1"       # Mandatory.
  Bus                 "i2c-0"       # Can have more than one bus.
  Address             0x30          # Optional, if missing the default address will be used.
  LogInstant          true          # Optional, sets whether to log instant field values.
  LogAxes             true          # Optional, sets whether to log individual axes values.
  LogEuclidean        true          # Optional, sets whether to log the Euclidean norm of all
                                    # axes. On a common magnetometer with 3-dimensional axes in
                                    # orthogonal directions, this gives the magnitude of the
                                    # magnetic field.
  LogDelta            false         # Optional, sets whether to log the changes in axes values,
                                    # and the Euclidean norm, if enabled.
  LogTemperature      true          # Optional, sets whether to log the temperature sensor
                                    # readings, if the sensor has one.
  Alpha               1.0           # Optional, sets the first-order IIR low-pass filter parameter
                                    # for axes values, and the Euclidean norm, if enabled. A value
                                    # of 1.0 disable low-pass filtering, while a value of 0 locks
                                    # the channels to their initial values (so do not do that).
  DeltaAlpha          0.0001        # Optional, sets the first-order IIR low-pass filter parameter
                                    # for the changes. A value of 0 simply subtracts the very
                                    # first measurement from each measurements. A value of 1.0
                                    # will result in all the changes being zero since it only
                                    # accepts infinitely high frequencies (so do not do that).
                                    # Normally you would want a value close to 0.
</Module>
'''

# Dict of how config entries should be parsed:
# {key in collectd.conf: (expected type, append, defaults)}
config_keys = {
  'Driver'        : ('driver'            , False, None  ),
  'Bus'           : ('bus'               , True , None  ),
  'Address'       : ('integer_expression', False, None  ),
  'LogInstant'    : ('boolean'           , False, True  ),
  'LogAxes'       : ('boolean'           , False, True  ),
  'LogEuclidean'  : ('boolean'           , False, True  ),
  'LogDelta'      : ('boolean'           , False, False ),
  'LogTemperature': ('boolean'           , False, True  ),
  'Alpha'         : ('fraction'          , False, 1.0   ),
  'DeltaAlpha'    : ('fraction'          , False, 0.0001),
}

plugin = MultiInstanceCollectdPlugin(config_keys, Instance, magnetometers)

# NOTE: collectd very annoying infer plugin by the module containing the method, so some wrapping is
# needed (aliasing alone won't work either)

def do_config(*args, **kwargs):
  plugin.do_config(*args, **kwargs)

def do_init(*args, **kwargs):
  plugin.do_init(*args, **kwargs)

def do_read(*args, **kwargs):
  plugin.do_read(*args, **kwargs)

collectd.register_config(do_config)
collectd.register_init(do_init)
collectd.register_read(do_read)
