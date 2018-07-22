#!/usr/bin/env python

# Monitors hwmon fan PWM duty cycle (how hard your fan is trying to work)
# Useful if hardware or automatic fan speed control is available

import collectd, socket
import os, fnmatch, re
import sys, traceback

def configure_callback(conf):
  collectd.info('Configured with')

def read(data = None):
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'pwm'

  reobj = re.compile('pwm[0-9]+$')

  for hwmon in os.listdir('/sys/class/hwmon'):
    for fn in os.listdir('/sys/class/hwmon/' + hwmon):
      if reobj.match(fn):
        try:
          f = open('/sys/class/hwmon/' + hwmon + '/' + fn, 'r')
          vl.dispatch(type = 'fanspeed', type_instance = hwmon + fn, values = [f.read()])
          f.close()
        except:
          exc_type, exc_value, exc_traceback = sys.exc_info()
          collectd.warning(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
          pass

collectd.register_config(configure_callback)
collectd.register_read(read)
