#!/usr/bin/env python

# Based on SGP30 code at: https://github.com/pimoroni/sgp30-python
# TODO: sink for humidity data, raw h2 and ethanol signals (need s_ref)

import time
import struct
import threading

import collectd
from envsensor._smbus2 import SMBus
from envsensor._utils import logi, logw, loge, get_i2c_bus_number, i2c_rdwr_read, i2c_rdwr_write

class SensorNotReadyError(Exception):
  pass

class SGP30:
  # NOTE: SGP30's address is always 0x58. Only 1 sensor can be on a bus unless an address translator
  # is used.
  I2C_ADDR              = 0x58
  EXPECTED_PRODUCT_TYPE = 0x0
  EXPECTED_FEATSET_MIN  = 0x20
  EXPECTED_TEST_RESULT  = 0xd400

  # {command name, (command word, parameter word count, response word count, max wait millis)}
  # For parameter/response, each word is 3 bytes due to the inclusion of CRC
  commands = {
      'init_iaq'                : (0x2003, 0, 0,  10),
      'measure_iaq'             : (0x2008, 0, 2,  12),
      'get_iaq_baseline'        : (0x2015, 0, 2,  10),
      'set_iaq_baseline'        : (0x201e, 2, 0,  10),
      'set_humidity'            : (0x2061, 1, 0,  10),
      'measure_test'            : (0x2032, 0, 1, 220),
      'get_feature_set_version' : (0x202f, 0, 1,  10),
      'measure_raw_signals'     : (0x2050, 0, 2,  25),
      'get_serial_id'           : (0x3682, 0, 3,  10),
      # Available in feature set 0x0022
      'get_tvoc_baseline'       : (0x20b3, 0, 1,  10),
      'set_tvoc_baseline'       : (0x2077, 1, 0,  10),
  }

  def __init__(self, bus, log_baseline, i2c_addr = I2C_ADDR):
    self.bus = bus
    self.log_baseline = log_baseline
    self._i2c_dev = SMBus(get_i2c_bus_number(bus))
    self._i2c_addr = i2c_addr
    self._ready = False
    test_result = self.command('measure_test')[0]
    if test_result != self.EXPECTED_TEST_RESULT:
      raise IOError('Sensor self-test failed (0x{:04x})!'.format(test_result))
    self.command('init_iaq')
    logi(
        'Initialized sensor with ID {:012x} on {}, feature set 0x{:02x}'
            .format(self.get_unique_id(), self.bus, self.get_feature_set_version()[1]))

  def get_air_quality(self):
    eco2, tvoc = self.command('measure_iaq')
    if not self._ready and eco2 == 400 and tvoc == 0:
      raise SensorNotReadyError()
    else:
      self._ready = True # no more checks
      return eco2, tvoc

  def get_unique_id(self):
    result = self.command('get_serial_id')
    return result[0] << 32 | result[1] << 16 | result[2]

  def get_feature_set_version(self):
    result = self.command('get_feature_set_version')[0]
    return (result & 0xf000) >> 12, result & 0x00ff

  def get_baseline(self):
    eco2, tvoc = self.command('get_iaq_baseline')
    return eco2, tvoc

  def set_baseline(self, eco2, tvoc):
    # For whatever reason the sequence has to be inverted...
    self.command('set_iaq_baseline', (tvoc, eco2))

  def command(self, command_name, parameters = None):
    if parameters is None:
      parameters = []
    parameters = list(parameters)
    cmd, param_len, response_len, wait_millis = self.commands[command_name]
    if len(parameters) != param_len:
      raise ValueError(
          "{} wants {} parameters, got {}".format(command_name, param_len, len(parameters)))

    parameters_out = [cmd]
    for i in range(len(parameters)):
      parameters_out.append(parameters[i])
      parameters_out.append(SGP30.calculate_crc_for_word(parameters[i]))
    data_out = struct.pack('>H' + ('HB' * param_len), *parameters_out)

    i2c_rdwr_write(self._i2c_dev, self._i2c_addr, data_out)
    time.sleep(wait_millis / 1000.)

    if response_len > 0:
      # Each parameter is a word (2 bytes) followed by a CRC (1 byte)
      buf = i2c_rdwr_read(self._i2c_dev, self._i2c_addr, response_len * 3)
      response = struct.unpack('>' + ('HB' * response_len), buf)

      verified = []
      for i in range(response_len):
        offset = i * 2
        value, crc = response[offset:offset + 2]
        if crc != SGP30.calculate_crc_for_word(value):
          raise IOError("Invalid CRC in response")
        verified.append(value)
      return verified

  def calculate_crc_for_word(data):
    crc = 0xff # Initialization value
    for byte in [(data & 0xff00) >> 8, data & 0x00ff]:
      crc ^= byte
      for _ in range(8):
        if crc & 0x80:
          crc = (crc << 1) ^ 0x31 # XOR with polynominal
        else:
          crc <<= 1
    return crc & 0xff

keep_polling  = True
data          = []
data_lock     = threading.Lock()

# Read sensor at 1 Hz rate for optimal performance, and cache the results for dispatch
def insert_dummy_read():
  global data, sensors

  t_last_read = time.monotonic()
  while keep_polling:
    t_start = time.monotonic()
    elapsed = t_start - t_last_read
    t_last_read += 1.0
    if elapsed < 1.0:
      time.sleep(1.0 - elapsed)

    data_lock.acquire()
    data = []
    for sensor in sensors:
      data_instance = {'bus': sensor.bus}
      try:
        # Handle baseline first since it never raise SensorNotReadyError
        if sensor.log_baseline:
          data_instance['eco2_baseline'], data_instance['tvoc_baseline'] = sensor.get_baseline()
        data_instance['eco2'], data_instance['tvoc'] = sensor.get_air_quality()
      except SensorNotReadyError:
        logw('Sensor on {} not ready yet'.format(sensor.bus))
      except:
        loge('Failed to read sensor on {}'.format(sensor.bus))
      data.append(data_instance)
    data_lock.release()

poll_thread = threading.Thread(target = insert_dummy_read)

configs     = []
sensors     = []

'''
Config example:

Import "envsensor.sgp30"
<Module "envsensor.sgp30">
  Buses       "i2c-1" "i2c-10"
  Baseline    35620 37850   # Sets eCO2 and TVOC baseline resistance (otherwise sensor will guess).
  LogBaseline true          # Whether to log the above baselines, which are dynamically adjusted by
                            # the sensor internally.
</Module>
'''
def config(config_in):
  global configs

  instance_config = dict()
  instance_config['buses'] = []
  instance_config['log_baseline'] = False
  for node in config_in.children:
    key = node.key.lower()
    val = node.values

    if    key == 'buses':
      instance_config['buses'] += [s.lower() for s in val]
    elif  key == 'baseline':
      assert len(val) == 2
      assert isinstance(val[0], (int, float))
      assert isinstance(val[1], (int, float))
      instance_config['baseline'] = (round(val[0]), round(val[1]))
    elif  key == 'logbaseline':
      assert len(val) == 1
      assert isinstance(val[0], bool)
      instance_config['log_baseline'] = val[0]
    else:
      raise KeyError('Unknown config key: ' + node.key)

  configs.append(instance_config)

def init():
  global sensors, configs

  if len(configs) == 0:
    logw('No config found, will not create any instance')

  for instance_config in configs:
    for bus in instance_config['buses']:
      try:
        sensor = SGP30(bus, instance_config['log_baseline'])
        if 'baseline' in instance_config.keys():
          eco2, tvoc = instance_config['baseline']
          sensor.set_baseline(eco2, tvoc)
        sensors.append(sensor)
      except:
        loge('Failed to init sensor on {}'.format(bus))

  if len(configs) != 0:
    poll_thread.start()

def read():
  global data

  vl = collectd.Values(type = 'gauge', plugin = 'envsensor')
  data_lock.acquire()
  for data_instance in data:
    bus = data_instance['bus']
    if 'eco2' in data_instance.keys() and 'tvoc' in data_instance.keys():
      vl.type_instance = 'SGP30'
      vl.dispatch(
          plugin_instance = bus + '_eCO2-ppm',
          values = [data_instance['eco2']])
      vl.dispatch(
          plugin_instance = bus + '_TVOC-ppb',
          values = [data_instance['tvoc']])
    if 'eco2_baseline' in data_instance.keys() and 'tvoc_baseline' in data_instance.keys():
      vl.plugin_instance = bus + '_baseline'
      vl.dispatch(
          type_instance = 'SGP30_eCO2',
          values = [data_instance['eco2_baseline']])
      vl.dispatch(
          type_instance = 'SGP30_TVOC',
          values = [data_instance['tvoc_baseline']])
  data = []
  data_lock.release()

def shutdown():
  global keep_polling

  keep_polling = False
  if poll_thread.is_alive():
    poll_thread.join()

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
collectd.register_shutdown(shutdown)
