#!/usr/bin/env python

# Simple test fixture for collectd python plugins, which fakes a collectd module
# Usage: python _test_fixture.py [plugin_name_without_.py]

import sys

class collectd:
  def __init__(self):
    self.f_config   = None
    self.f_init     = None
    self.f_read     = None
    self.f_shutdown = None
    self.f_write    = None
    self.f_flush    = None
    self.f_log      = None

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
    self.f_config   = None
  def unregister_init(self):
    self.f_init     = None
  def unregister_read(self):
    self.f_read     = None
  def unregister_shutdown(self):
    self.f_shutdown = None
  def unregister_write(self):
    self.f_write    = None
  def unregister_flush(self):
    self.f_flush    = None
  def unregister_log(self):
    self.f_log      = None

  def error(self, s):
    print 'Plugin Error: '    + s
  def warning(self, s):
    print 'Plugin Warning: '  + s
  def notice(self, s):
    print 'Plugin Notice: '   + s
  def info(self, s):
    print 'Plugin Info: '     + s
  def debug(self, s):
    print 'Plugin Debug: '    + s

  class Values:
    def __init__(self, type):
      print 'Values.init: type = ' + type
      self.plugin_instance = None
      self.type_instance = None
      self.plugin = None
      self.host = '(default)'
      self.time = 0
      self.interval = 0

    def dispatch(self, type, values, plugin_instance = None, type_instance = None, plugin = None, host = None, time = None, interval = None):
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
      print 'Dispatch: type = {}; values = {}; p_instance = {}; t_instance = {}; plugin = {}; host = {}; time = {}; interval = {}'.format(type, values, plugin_instance, type_instance, plugin, host, time, interval)

if __name__ == '__main__':
  sys.modules['collectd'] = collectd() # Override system's collectd module, like LD_PRELOAD for python
  dut = __import__(sys.argv[1])
  dut.read()
