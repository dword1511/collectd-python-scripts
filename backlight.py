#!/usr/bin/env python

# Monitors backlight brightness

import collectd, socket
import os
import sys, traceback

def configure_callback(conf):
  collectd.info('Configured with')

def read(data = None):
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'backlight'
  vl.host = socket.getfqdn()

  for backlight in os.listdir('/sys/class/backlight'):
    try:
      f = open('/sys/class/backlight/' + backlight + '/actual_brightness', 'r') # brightness != actual_brightness especially when lid is closed.
      bl_now = float(f.read());
      f.close()
      f = open('/sys/class/backlight/' + backlight + '/max_brightness', 'r')
      bl_max = float(f.read());
      f.close()

      vl.dispatch(type = 'percent', type_instance = backlight, values = [bl_now / bl_max * 100])
    except:
      exc_type, exc_value, exc_traceback = sys.exc_info()
      collectd.warning(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
      pass

collectd.register_config(configure_callback)
collectd.register_read(read)
