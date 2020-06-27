#!/usr/bin/env python

import time

import collectd
from envsensor._smbus2 import SMBus
from envsensor._utils import logi, logw, loge

class HDC2080:
  # HDC2080's address is either 0x40 or 0x41 (unless a translator is used).
  I2C_ADDR            = 0x40

  REG_TEMP_L          = 0x00
  REG_TEMP_H          = 0x01
  REG_HUM_L           = 0x02
  REG_HUM_H           = 0x03
  REG_INT             = 0x04
  INT_DRDY_STATUS     = (1 << 7)
  INT_TH_STATUS       = (1 << 6)
  INT_TL_STATUS       = (1 << 5)
  INT_HH_STATUS       = (1 << 4)
  INT_HL_STATUS       = (1 << 3)
  REG_TEMP_MAX        = 0x05
  REG_HUM_MAX         = 0x06
  REG_INT_EN          = 0x07
  INT_EN_DRDY         = (1 << 7)
  INT_EN_TH           = (1 << 6)
  INT_EN_TL           = (1 << 5)
  INT_EN_HH           = (1 << 4)
  INT_EN_HL           = (1 << 3)
  REG_TEMP_OFFSET_ADJ = 0x08
  REG_HUM_OFFSET_ADJ  = 0x09
  REG_TEMP_THR_L      = 0x0a
  REG_TEMP_THR_R      = 0x0b
  REG_RH_THR_L        = 0x0c
  REG_RH_THR_H        = 0x0d
  REG_SYS_CFG         = 0x0e
  SYS_CFG_SOFT_RST    = (1 << 7)
  SYS_CFG_AMM_MANUAL  = (0 << 4)
  SYS_CFG_AMM_2MIN    = (1 << 4)
  SYS_CFG_AMM_1MIN    = (2 << 4)
  SYS_CFG_AMM_10SEC   = (3 << 4)
  SYS_CFG_AMM_5SEC    = (4 << 4)
  SYS_CFG_AMM_1HZ     = (5 << 4)
  SYS_CFG_AMM_2HZ     = (6 << 4)
  SYS_CFG_AMM_5HZ     = (7 << 4)
  SYS_CFG_HEAT_EN     = (1 << 3)
  SYS_CFG_INT_EN      = (1 << 2)
  SYS_CFG_INT_POL     = (1 << 1)
  SYS_CFG_INT_MODE    = (1 << 0)
  REG_MEAS_CFG        = 0x0f
  MEAS_CFG_TRES_14BIT = (0 << 6)
  MEAS_CFG_TRES_11BIT = (1 << 6)
  MEAS_CFG_TRES_9BIT  = (2 << 6)
  MEAS_CFG_HRES_14BIT = (0 << 4)
  MEAS_CFG_HRES_11BIT = (1 << 4)
  MEAS_CFG_HRES_9BIT  = (2 << 4)
  MEAS_CFG_RHT        = (0 << 1)
  MEAS_CFG_TEMP_ONLY  = (1 << 1)
  MEAS_CFG_MEAS_TRIG  = (1 << 0)
  REG_MAN_ID_L        = 0xfc
  REG_MAN_ID_H        = 0xfd
  MAN_ID              = 0x5449 # NOTE: datasheet got tricked by endianess, DEV_ID was correct though
  REG_DEV_ID_L        = 0xfe
  REG_DEV_ID_H        = 0xff
  DEV_ID              = 0x07d0

  meas_cfg_default    = MEAS_CFG_TRES_14BIT | MEAS_CFG_HRES_14BIT | MEAS_CFG_RHT

  def __init__(self, busno, address = I2C_ADDR):
    self.busno = busno
    self.bus = SMBus(busno)
    self.address = address

    self._check_id()
    self._reset()

  def _check_id(self):
    man_id = self.bus.read_word_data(self.address, self.REG_MAN_ID_L)
    dev_id = self.bus.read_word_data(self.address, self.REG_DEV_ID_L)
    if man_id != self.MAN_ID or dev_id != self.DEV_ID:
      raise IOError(
          'Incorrect manufacture ID 0x{:04x} and/or device ID 0x{:04x} (expected 0x{:04x} 0x{:04x})'
              .format(man_id, dev_id, self.MAN_ID, self.DEV_ID))

  def _reset(self):
    self.bus.write_byte_data(self.address, self.REG_SYS_CFG, self.SYS_CFG_SOFT_RST)
    self.bus.write_byte_data(self.address, self.REG_SYS_CFG, self.SYS_CFG_AMM_MANUAL)
    self.bus.write_byte_data(self.address, self.REG_MEAS_CFG, self.meas_cfg_default)

  def read(self):
    # Clear stale flags
    self.bus.read_byte_data(self.address, self.REG_MEAS_CFG)
    # Start measurement
    self.bus.write_byte_data(
        self.address, self.REG_MEAS_CFG, self.meas_cfg_default | self.MEAS_CFG_MEAS_TRIG)
    # Wait for measurement to finish
    time.sleep(0.01) # actual: 1.27 ms typical for RH+T
    if not self.bus.read_byte_data(self.address, self.REG_INT) & self.INT_DRDY_STATUS:
      raise TimeoutError('Measurement timed out')

    temp = self.bus.read_word_data(self.address, self.REG_TEMP_L)
    rh = self.bus.read_word_data(self.address, self.REG_HUM_L)
    temp = temp * 165. / (1 << 16) - 40.
    rh = rh * 100. / (1 << 16)

    return temp, rh

buses     = None
addresses = []
sensors   = []

'''
Config example:

Import "envsensor.htu21d"
<Module "envsensor.htu21d">
  Bus         1 2 3
  Address     0x40 0x41
</Module>
'''
def config(config_in):
  global buses, addresses

  for node in config_in.children:
    key = node.key.lower()
    val = node.values
    # All config values must be integers (may come in as float type)
    for v in val:
      assert isinstance(v, (int, float))

    if key == 'bus':
      buses = val
    elif key == 'address':
      addresses = val
    else:
      logw('Skipping unknown config key "{}"'.format(key))

def init():
  global sensors, buses, addresses

  if not buses:
    buses = [1]
    logi('Buses not set, defaulting to {}'.format(str(buses)))

  for bus in buses:
    if bus is None:
      continue
    bus = round(bus)
    if not addresses:
      try:
        sensor = HDC2080(bus)
        sensors.append(sensor)
        logi('Initialized sensor on i2c-{}, address 0x{:02x}'.format(bus, sensor.address))
      except:
        loge('Failed to init sensor on i2c-{} with default address'.format(bus))
    else:
      for address in addresses:
        address = round(address)
        try:
          sensor = HDC2080(bus, address)
          sensors.append(sensor)
          logi('Initialized sensor on i2c-{}, address 0x{:02x}'.format(bus, address))
        except:
          loge('Failed to init sensor on i2c-{}, address 0x{:02x}'.format(bus, address))

def read(data = None):
  global sensors

  vl = collectd.Values(plugin = 'envsensor')
  for sensor in sensors:
    vl.plugin_instance = 'i2c-{}'.format(sensor.busno)
    vl.type_instance = 'HDC2080_0x{:02x}'.format(sensor.address)
    try:
      temp, rh = sensor.read()
      vl.dispatch(type = 'temperature', values = [temp])
      vl.dispatch(type = 'humidity', values = [rh])
    except:
      loge(
          'Failed to read temperature on i2c-{}, address 0x{:02x}'
              .format(sensor.busno, sensor.address))

collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
