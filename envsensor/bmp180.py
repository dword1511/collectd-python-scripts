#!/usr/bin/env python

# Depends on: adafruit-bmp

# TODO: config for I2C/SPI, bus number, address, multi-sensor (enumerate)

import collectd
import Adafruit_BMP.BMP085 as BMP085

def read(data = None):
  sensor = BMP085.BMP085()
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'
  #vl.plugin_instance = 'BMP180'

  try:
    vl.dispatch(type = 'temperature', type_instance = 'BMP180', values = [sensor.read_temperature()])
  except:
    pass

  try:
    vl.dispatch(type = 'pressure', type_instance = 'BMP180', values = [float(sensor.read_pressure())])
  except:
    pass

collectd.register_read(read)
