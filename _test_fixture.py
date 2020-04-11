#!/usr/bin/env python3

# Simple test fixture for collectd python plugins, which fakes a collectd module
# Usage: python _test_fixture.py [plugin_name_without_.py]

from __future__ import print_function

import sys

class _collectd:
  def _def_config(self, config_in = None):
    print('Default config')

  def _def_init(self):
    print('Default init')

  def _def_read(self, data = None):
    print('Default read')

  def _def_shutdown(self):
    print('Default shutdown')

  def _def_write(self):
    print('Default write')

  def _def_flush(self):
    print('Default flush')

  def _def_log(self):
    print('Default log')

  def __init__(self):
    self.f_config   = self._def_config
    self.f_init     = self._def_init
    self.f_read     = self._def_read
    self.f_shutdown = self._def_shutdown
    self.f_write    = self._def_write
    self.f_flush    = self._def_flush
    self.f_log      = self._def_log

  def register_config(self, f):
    self.f_config   = f
  def register_init(self, f):
    self.f_init     = f
  def register_read(self, f):
    self.f_read     = f
  def register_shutdown(self, f):
    self.f_shutdown = f
  def register_write(self, f):
    self.f_write    = f
  def register_flush(self, f):
    self.f_flush    = f
  def register_log(self, f):
    self.f_log      = f

  def unregister_config(self):
    self.f_config   = self._def_config
  def unregister_init(self):
    self.f_init     = self._def_init
  def unregister_read(self):
    self.f_read     = self._def_read
  def unregister_shutdown(self):
    self.f_shutdown = self._def_shutdown
  def unregister_write(self):
    self.f_write    = self._def_write
  def unregister_flush(self):
    self.f_flush    = self._def_flush
  def unregister_log(self):
    self.f_log      = self._def_log

  def error(self, s):
    print('Plugin Error: '    + s)
  def warning(self, s):
    print('Plugin Warning: '  + s)
  def notice(self, s):
    print('Plugin Notice: '   + s)
  def info(self, s):
    print('Plugin Info: '     + s)
  def debug(self, s):
    print('Plugin Debug: '    + s)

  class Values:
    def __init__(self, type):
      print('Values.init: type = ' + type)
      self.plugin_instance = ''
      self.type_instance = ''
      self.plugin = None
      self.host = '(default)'
      self.time = 0
      self.interval = 0

    def dispatch(self, type, values, plugin_instance = None, type_instance = None, plugin = None, host = None, time = None, interval = None):
      if not isinstance(values, (list, tuple)):
        raise ValueError('values must be list or tuple')
      if plugin_instance is None:
        plugin_instance = self.plugin_instance
      if type_instance is None:
        type_instance = self.type_instance
      if plugin is None:
        plugin = self.plugin
      if host is None:
        host = self.host
      if time is None:
        time = self.time
      if interval is None:
        interval = self.interval
      if None in locals():
        raise ValueError('no argument shall be None')
      print('Dispatch: type = "{}"; values = {}; p_instance = "{}"; t_instance = "{}"; plugin = "{}"; host = "{}"; time = {}; interval = {}'
            .format(type, values, plugin_instance, type_instance, plugin, host, time, interval))

class _Config:
  def __init__(self):
    self.parent = None
    self.key = None
    self.value = None
    self.children = ()

if __name__ == '__main__':
  if len(sys.argv) is not 2:
    print('Usage: {} [plugin_name_without_.py]'.format(sys.argv[0]))
    sys.exit(1)

  # Override system's collectd module, like LD_PRELOAD for python
  collectd = _collectd()
  sys.modules['collectd'] = collectd

  dut = __import__(sys.argv[1], fromlist=['*'])
  collectd.f_config(_Config())
  collectd.f_init()
  collectd.f_read()
  collectd.f_shutdown()
