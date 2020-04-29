import traceback as tb
import inspect

import collectd

def get_calling_module_name():
  '''
  Returns the name of the module containing the caller, other than this module.
  '''

  get_name = lambda f: inspect.getmodulename(f.f_code.co_filename)
  this_name = __name__.split('.')[-1]
  frame = inspect.currentframe().f_back
  while frame != None and get_name(frame) == this_name:
    frame = frame.f_back
  return '(unknown)' if frame == None else get_name(frame)

def get_classes(module):
  '''
  Returns a list of classes in the given module.
  '''

  return [
      c[0] for c in inspect.getmembers(module, inspect.isclass)
          if c[1].__module__ == module.__name__]

def sanitize_driver_name(driver):
  '''
  Returns a list of driver names where symbols in common sensor model names are replaced with '_'.

  This allows users to use actual part numbers, which may contain weird characters.
  '''

  return driver.replace('-', '_').replace(' ', '_')

def check_value_by_type(val, expected_type, drivers):
  '''
  Checks whether a value in collectd config matches the expected type. Raises ValueError if not.

  TODO: double-check: collectd may return all numbers as float
  '''

  if    expected_type == 'bus':
    if not isinstance(val, str):
      raise ValueError('"{}" is not a valid bus'.format(val))
    # Driver shall perform further checks to ensure a supported bus is passed
  elif  expected_type == 'driver':
    if not isinstance(val, str) or sanitize_driver_name(val) not in drivers:
      raise ValueError('Driver "{}" does not exist'.format(val))
  elif  expected_type == 'integer_expression':
    if not isinstance(val, (int, str)) or (isinstance(val, str) and '.' in val):
      raise ValueError('"{}" is not a valid integer'.format(val))
    # Check whether it can be converted
    int(val, 0)
  elif  expected_type == 'number':
    if not isinstance(val, (float, int)):
      raise ValueError('"{}" is not a valid number'.format(val))
  elif  expected_type == 'fraction':
    if not isinstance(val, float) or val > 1 or val < 0:
      raise ValueError('"{}" is not a valid fraction'.format(val))
  elif  expected_type == 'boolean':
    if not isinstance(val, bool):
      raise ValueError('"{}" is not a valid boolean'.format(val))
  else:
    raise TypeError('Internal error, "{}" is not a valid type'.format(val))

def parse_collectd_config(config_keys, config, drivers):
  '''
  Checks and parses collectd config into a dict according to config keys defined in config_keys.

  Structure of config_keys:
    {key in collectd.conf: (expected type, append, defaults)}
  '''

  # Set defaults and prepare list for appendable values
  instance_config = dict()
  for k, v in config_keys.items():
    _, append, defaults = v
    if append:
      instance_config[k] = []
    elif defaults != None:
      instance_config[k] = defaults

  # Parse config
  config_keys_case_insensitive = {k.lower(): (k, v) for k, v in config_keys.items()}
  for node in config.children:
    key = node.key.lower()

    if key in config_keys_case_insensitive.keys():
      variable_name = config_keys_case_insensitive.get(key)[0]
      expected_type, append, _ = config_keys_case_insensitive.get(key)[1]
      if len(node.values) != 1:
        raise ValueError('Config key not followed by exactly 1 value: ' + str(node.values))
      val = node.values[0]
      check_value_by_type(val, expected_type, get_classes(drivers))
      if append:
        instance_config[variable_name].append(val)
      else:
        instance_config[variable_name] = val
    else:
      raise KeyError('Invalid config key "{}"'.format(node.key))

  # Check mandatory fields
  if len(instance_config['Bus']) > 0 and 'Driver' in instance_config.keys():
    # Allow users to use actual part numbers, which may contain weird characters
    instance_config['Driver'] = (getattr(drivers, sanitize_driver_name(instance_config['Driver'])))
    return instance_config
  else:
    raise KeyError('Mandatory config fields "Driver" and/or "Bus" missing')

def get_i2c_bus_number(s):
  '''
  Extracts the bus number from strings like "i2c-1".
  '''

  if not s.startswith('i2c-'):
    raise ValueError('Unsupported bus: ' + s)
  return int(s[len('i2c-'):], 10)

def get_word_le(block, offset, base = 0):
  '''
  Extracts a 16-bit little-endian value from a block of data. The offset must be aligned.
  '''

  offset -= base
  return block[offset] | block[offset + 1] << 8

def get_24bit_le(block, offset, base = 0):
  '''
  Extracts a 24-bit little-endian value from a block of data. The offset must be aligned.
  '''

  offset -= base
  return block[offset] | block[offset + 1] << 8 | block[offset + 2] << 16

def uw_cm2_to_w_m2(uw_cm2):
  '''
  Converts an irradiance number from uW/cm2 to W/m2.
  '''

  return uw_cm2 * 1.e4 / 1.e6

def loge(log, name = None):
  '''
  Logs an error with stack trace.
  '''

  if name == None:
    name = get_calling_module_name()
  collectd.error(name + ': ' + log + '\n' + tb.format_exc())

def logw(log, name = None):
  '''
  Logs an warning.
  '''

  if name == None:
    name = get_calling_module_name()
  collectd.warning(name + ': ' + log)

def logi(log, name = None):
  '''
  Logs information.
  '''

  if name == None:
    name = get_calling_module_name()
  collectd.info(name + ': ' + log)

def logd(log, name = None):
  '''
  Logs debug information.
  '''

  if name == None:
    name = get_calling_module_name()
  collectd.debug(name + ': ' + log)

class MultiInstanceCollectdPlugin():
  '''
  Creates collectd plugin instances based on specified config keys, instance class, and drivers.

  See parse_collectd_config() for a definition of the config keys.

  Instance class must have the following functions:
      __init__(config, bus), where config is generated by parse_collectd_config() & bus is a string;
      dispatch(vl), where vl is a collectd.Values instance to which values should be dispatched.

  Drivers should be a module containing the individual drivers that will be utilized by the instance
  class, each as a separate class.
  '''

  def __init__(self, config_keys, instance_class, drivers):
    self._plugin_name = get_calling_module_name()
    logi('Loaded with drivers: ' + str(get_classes(drivers)), self._plugin_name)
    self._config_keys = config_keys
    self._instance_class = instance_class
    self._drivers = drivers
    self._configs = []
    self._instances = []
    # NOTE: collectd callbacks must be registered in the plugin module

  def do_config(self, config):
    '''
    Configures an instance.

    This method will be called multiple times by collectd if there are multiple config blocks,
    creating multiple instances with potentially different drivers.

    If there is an error in the config, an exception will be raised.
    '''

    self._configs.append(parse_collectd_config(self._config_keys, config, self._drivers))

  def do_init(self):
    '''
    Initializes instances according to the configs.
    '''

    if len(self._configs) == 0:
      logw('No config found, will not create any instance', self._plugin_name)
    for instance_config in self._configs:
      logd('Handling config: ' + str(instance_config), self._plugin_name)
      for bus in instance_config['Bus']:
        driver = instance_config['Driver'].__name__
        try:
          self._instances.append(self._instance_class(instance_config, bus))
          logi('Initialized instance for "{}" on bus {}'.format(driver, bus), self._plugin_name)
        except:
          loge(
              'Instance for "{}" on bus {} failed to initialize'.format(driver, bus),
              self._plugin_name)

  def do_read(self):
    '''
    Dispatches values from all instances.
    '''

    vl = collectd.Values(plugin = 'envsensor')
    for instance in self._instances:
      try:
        instance.dispatch(vl)
      except:
        loge('Dispatch failed!', self._plugin_name)
