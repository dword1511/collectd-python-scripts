'''
Generic ambient light sensor plugin.

Features:
* Analog gain support
* Integration time support
* Automatic gain/integration time control for utilizing the full dynamic range of the sensor
* Multi-channel support (Visible + IR, RGB, UVA + UVB, ALS + PS, etc.)
* Radiometric (irradiance) and perceptive (photometry e.g. illuminance, and imperical e.g. UV index)
* Multiple instance support, each with separate config and optionally multiple sensors
'''

import collectd

from envsensor._utils import logi, MultiInstanceCollectdPlugin
import envsensor._lightsensors as lightsensors

class Instance:
  '''
  Handles an instance of plugin on a particular bus with a specified driver.

  Will throw an exception if initialization fails.

  The driver needs to implement the following functions:
  * __init__(bus, address = None): create a sensor object on the bus specified by string in the bus
        parameter, optionally with an address. If no address is supplied, the default shall be used.
        Each sensor may have multiple channels.
  * get_channel_modes(): returns a list of dicts, one for each groups of channels that must shared
        the same sensor setting. This should have the following structure:
          [
            {
              'channels': {
                'name': whether is radiometric (True or False),
                ...
              },
              'gain_table': {
                total gain 1: (analog gain 1, integration time 1),
                ...
              }
            },
            ...
          ]
        The name field in channels should be human-friendly. Examples of the name field: "Visible",
        "Full", "IR", "Red", "UVA", "940nm", "Proximity".
        If the channel is perceptive (radiometric is False), the channel name should be common for
        different sensor models, likely units, e.g. "lux", "UVI". These channels should be derived
        from the measurements of one or multiple radiometric channels.
        The analog gain should be a multiplier, the minimum analog gain must be 1.
        Integration time must have the unit seconds.
        Total gain is relative and the lowest should be 1. The gain should be a product of analog
        gain and the integration time divided by the minimum integration time.
        These information will be used for automatic gain/integration time control as well as
        dispatching sensor values.
  * set_channel_mode(name, again, itime): sets the analog gain and integration time of the sensor,
        for channel with the name given (as well as all the channels in the group since they must
        have the same settings).
  * read_channels(): triggers one measurement on all channels, and returns the results.
        This function shall block during the measurement. The returned results should have the
        following structure:
          {
            'name': {
              'value': float-point value converted to appropriate units
              'saturation': a fraction showing how saturated the underlying raw value is
              'again': analog gain used
              'itime': integration time used
            },
            ...
          }
        The values for radiometric channels shall have the unit of Watts per square meter.
          Note: datasheets usually gives sensitivity as how many counts the sensor will measure for
          each channel, under certain analog gain and integration time, for certain irradiance in
          microwatts per square centimeter (uW/cm2). Convert it to W/m2 by dividing it with 100,
          then divide by the counts given in the datasheet. Finally, convert the counts returned by
          the sensor to irradiance by multiplying this sensitivity, factoring the impact of total
          gain (e.g. with analog gain four times the value used in the datasheet and integration
          time twice the value used in datasheet, the sensitivity needs to be divided by 8).
        Radiometric values cannot be negative. Some sensors have compensation mechanisms which
        subtracts the channel value by a value from a reference (dark) sensor. This may
        occasionally result in negative values and should be clipped to 0.
        Non-radiometric (perceptive) channels shall have their value clipped to a reasonable range.
        e.g. UVI (UV index) should have a range of [0, 12] (with 12 meaning 11+), and lux should
        never be negative.
        Saturation is the obtained count divided by maximum possible count for the given
        configuration. Must be a fraction in the range of (0, 1]. In case the sensor returns 0
        count, treat the count as 1 when computing the fraction.
          Note: this treatment should be natural to do, i.e. for a 16-bit sensor, simply do
          (count + 1) / (1 << 16).
        The saturation values will be used for automatic gain/integration time control.
        For non-radiometric channels, maximum saturation of radiometric channels used to derive it
        should be used.
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

    # Obtain sensor characteristics and filter out settings disallowed by config
    self.channel_modes = self.sensor.get_channel_modes()
    for group in self.channel_modes:
      if 'AnalogGain' in config.keys():
        again = config['AnalogGain']
        group['gain_table'] = (
            dict(filter(lambda k_v: k_v[1][0] == again, group['gain_table'].items())))
      if 'IntegrationTime' in config.keys():
        itime = config['IntegrationTime']
        group['gain_table'] = (
            dict(filter(lambda k_v: k_v[1][1] == itime, group['gain_table'].items())))
      if 'MaxIntegrationTime' in config.keys():
        max_itime = config['MaxIntegrationTime']
        group['gain_table'] = (
            dict(filter(lambda k_v: k_v[1][1] <= max_itime, group['gain_table'].items())))
      if len(group['gain_table']) == 0:
        raise RuntimeError('No supported settings match config given')
    self.log('permitted channel modes: ' + str(self.channel_modes))

    # Build a dict of channel properties for convenience
    self.is_radiometric = dict()
    self.min_itime = dict()
    for group in self.channel_modes:
      for name, radiometric in group['channels'].items():
        self.is_radiometric[name] = radiometric
        self.min_itime[name] = group['gain_table'][1][1]

  def log(self, msg):
    logi('{} on bus {}, {}'.format(self.driver_name, self.bus, msg))

  def measure(self):
    # Estimate proper setting
    for group in self.channel_modes:
      name = list(group['channels'].keys())[0]
      min_again, min_itime = group['gain_table'][1]
      self.sensor.set_channel_mode(name, min_again, min_itime)
    results_estimate = self.sensor.read_channels()

    # Optimize settings and try again (TODO: prioritize integration time)
    max_new_gain = 1
    for group in self.channel_modes:
      names = group['channels'].keys()
      max_saturation = max([results_estimate[n]['saturation'] for n in names])
      extra_gain = 1. / max_saturation / (1 + self.config['GainMargin'])
      new_gains = [gain for gain in group['gain_table'].keys() if gain <= extra_gain]
      if len(new_gains) == 0:
        new_gain = 1
      else:
        new_gain = max(new_gains)
      again, itime = group['gain_table'][new_gain]
      self.sensor.set_channel_mode(list(names)[0], again, itime)
      max_new_gain = max([max_new_gain, new_gain])
    if max_new_gain == 1:
      self.log('skipping second pass of measurements due to insufficient gain margin')
      return results_estimate
    else:
      results = self.sensor.read_channels()

    # Check saturated channels (due to dynamics) and revert them
    for name in results.keys():
      saturation = results[name]['saturation']
      if saturation > self.config['MaxSaturation']:
        self.log('reverting channel ' + str(names) + ' due to saturation: ' + str(saturation))
        results[name] = results_estimate[name]
    return results

  def dispatch(self, vl):
    for name, result in self.measure().items():
      value, saturation, again, itime = map(result.get, ('value', 'saturation', 'again', 'itime'))
      radiometric = self.is_radiometric[name]
      perceptive = not radiometric
      itime_gain = float(itime) / self.min_itime[name]
      # Skip if the config says this channel should be ignored
      if (
          (radiometric and not self.config['LogRadiometric'])
          or (perceptive and not self.config['LogPerceptive'])):
        continue

      # Log value
      if radiometric:
        vl.dispatch(
            type = 'count',
            plugin_instance = self.bus + '_irradiance-W-m2',
            type_instance = self.driver_name + '_' + name,
            values = [value])
      if perceptive:
        vl.dispatch(
            type = 'gauge',
            plugin_instance = self.bus + '_' + name,
            type_instance = self.driver_name,
            values = [value])

      # Log additional information as enabled by config, but only for radiometric channels
      if not radiometric:
        continue
      if self.config['LogSaturation']:
        vl.dispatch(
            type = 'percent',
            plugin_instance = self.bus,
            type_instance = self.driver_name + '_' + name,
            values = [saturation * 100])
      if self.config['LogIntegrationTime']:
        vl.dispatch(
            type = 'duration',
            plugin_instance = self.bus,
            type_instance = self.driver_name + '_' + name,
            values = [itime])
      if self.config['LogAnalogGain']:
        vl.dispatch(
            type = 'gauge',
            plugin_instance = self.bus + '_gain',
            type_instance = self.driver_name + '_' + name,
            values = [again])
      if self.config['LogTotalGain']:
        vl.dispatch(
            type = 'gauge',
            plugin_instance = self.bus + '_total-gain',
            type_instance = self.driver_name + '_' + name,
            values = [again * itime_gain])

'''
Example config block:
<Module "envsensor.lightsensor">
  Driver              "TSL2591"     # Mandatory, see _lightsensors.py for possible values.
  Bus                 "i2c-1"       # Mandatory.
  Bus                 "i2c-0"       # Can have more than one bus.
  Address             0x29          # Optional, if missing the default address will be used.
  LogRadiometric      true          # Optional, sets whether radiometric channels will be
                                    # recorded.
  LogPerceptive       true          # Optional, sets whether perceptive channels will be recorded.
  LogSaturation       false         # Optional, sets whether sensor saturation will be recorded.
  LogIntegrationTime  false         # Optional, sets whether integration time used will be
                                    # recorded.
  LogAnalogGain       false         # Optional, sets whether analog gain used will be recorded.
  LogTotalGain        false         # Optional, specifies whether the total gain used should be
                                    # recorded.
  MaxIntegrationTime  0.2           # Optional, sets maximum allowed integration time in seconds.
  GainMargin          0.5           # Optional, specifies margin for automatic gain/integration
                                    # time control.
  MaxSaturation       0.9           # Optional, specifies maximum saturation allowed for automatic
                                    # gain/integration time control.
  AnalogGain          1             # Optional, disables automatic analog gain control and use
                                    # specified value instead.
                                    # TODO: may make this a list.
  IntegrationTime     0.2           # Optional, disables automatic integration time control and
                                    # use specified value instead.
                                    # TODO: may make this a list.
</Module>
'''

# {key in collectd.conf: (expected type, append, defaults)}
config_keys = {
  'Driver'            : ('driver'            , False, None ),
  'Bus'               : ('bus'               , True , None ),
  'Address'           : ('integer_expression', False, None ),
  'LogRadiometric'    : ('boolean'           , False, True ),
  'LogPerceptive'     : ('boolean'           , False, True ),
  'LogSaturation'     : ('boolean'           , False, False),
  'LogIntegrationTime': ('boolean'           , False, False),
  'LogAnalogGain'     : ('boolean'           , False, False),
  'LogTotalGain'      : ('boolean'           , False, False),
  'MaxIntegrationTime': ('number'            , False, None ),
  'GainMargin'        : ('number'            , False, 0.5  ),
  'MaxSaturation'     : ('fraction'          , False, 0.9  ),
  'AnalogGain'        : ('number'            , False, None ),
  'IntegrationTime'   : ('number'            , False, None ),
}

plugin = MultiInstanceCollectdPlugin(config_keys, Instance, lightsensors)

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
