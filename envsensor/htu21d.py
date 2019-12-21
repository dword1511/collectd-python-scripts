#!/usr/bin/env python

# Original HTU21D code: https://github.com/jasiek/HTU21D/
# Did not use adafruit-circuitpython-htu21d as it does not support python2
# Did not use smbus/smbus2 because they flat cannot do some I2C transactions

# TODO: config for bus number, multi-sensor (enumerate)

import time

import collectd
from envsensor._i2cdev import I2C


class HTU21D:
  I2C_ADDR = 0x40
  CMD_TRIG_TEMP_HM = 0xE3
  CMD_TRIG_HUMID_HM = 0xE5
  CMD_TRIG_TEMP_NHM = 0xF3
  CMD_TRIG_HUMID_NHM = 0xF5
  CMD_WRITE_USER_REG = 0xE6
  CMD_READ_USER_REG = 0xE7
  CMD_RESET = 0xFE

  def __init__(self, busno):
    self.bus = I2C(busno)
    self.bus.set_addr(self.I2C_ADDR)

  def __del__(self):
    self.bus.close()

  def read_temperature(self):
    self.bus.write([self.CMD_TRIG_TEMP_NHM])
    time.sleep(0.1)
    msb, lsb, crc = self.bus.read(3)
    return -46.85 + 175.72 * (msb * 256 + lsb) / 65536

  def read_humidity(self):
    self.bus.write([self.CMD_TRIG_HUMID_NHM])
    time.sleep(0.1)
    msb, lsb, crc = self.bus.read(3)
    return -6 + 125 * (msb * 256 + lsb) / 65536.0

  def reset(self):
    self.bus.write([self.CMD_RESET])

def read(data = None):
  sensor = HTU21D(1)
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'envsensor'

  try:
    vl.dispatch(type = 'temperature', type_instance = 'HTU21D', values = [sensor.read_temperature()])
  except:
    pass

  try:
    vl.dispatch(type = 'humidity', type_instance = 'HTU21D', values = [sensor.read_humidity()])
  except:
    pass

def init():
  sensor = HTU21D(1)
  sensor.reset()

collectd.register_read(read)
collectd.register_init(init)
