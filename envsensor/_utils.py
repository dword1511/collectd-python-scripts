import traceback as tb
import inspect

import collectd

def get_calling_module_name():
  '''
  Returns the name of the module containing the caller.
  '''

  frame = inspect.currentframe().f_back.f_back
  return inspect.getmodulename(frame.f_code.co_filename)

def get_classes(module):
  '''
  Returns a list of classes in the given module.
  '''

  return [
      c[0] for c in inspect.getmembers(module, inspect.isclass)
          if c[1].__module__ == module.__name__]

def get_i2c_bus_number(s):
  if not s.startswith('i2c-'):
    raise ValueError('Unsupported bus: ' + s)
  return int(s[len('i2c-'):], 10)

def get_word_le(block, offset, base = 0):
  offset -= base
  return block[offset] | block[offset + 1] << 8

def get_24bit_le(block, offset, base = 0):
  offset -= base
  return block[offset] | block[offset + 1] << 8 | block[offset + 2] << 16

def uw_cm2_to_w_m2(uw_cm2):
  return uw_cm2 * 1.e4 / 1.e6

def loge(log):
  '''
  Logs an error with stack trace.
  '''

  collectd.error(get_calling_module_name() + ': ' + log + '\n' + tb.format_exc())

def logw(log):
  '''
  Logs an warning.
  '''

  collectd.warning(get_calling_module_name() + ': ' + log)

def logi(log):
  '''
  Logs information.
  '''

  collectd.info(get_calling_module_name() + ': ' + log)

def logd(log):
  '''
  Logs debug information.
  '''

  collectd.debug(get_calling_module_name() + ': ' + log)
