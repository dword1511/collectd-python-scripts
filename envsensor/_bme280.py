# Copyright (c) 2014 Adafruit Industries
# Author: Tony DiCola
# Author: Chi Zhang
#
# Based on the BMP280 driver with BME280 changes provided by
# David J Taylor, Edinburgh (www.satsignal.eu). Additional functions added
# by Tom Nardi (www.digifail.com)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import time

from envsensor._smbus2 import SMBus

# BME280 Addresses
BME280_I2CADDR_HI           = 0x77
BME280_I2CADDR_LO           = 0x76

# Operating Modes
BME280_OSAMPLE_1            = 1
BME280_OSAMPLE_2            = 2
BME280_OSAMPLE_4            = 3
BME280_OSAMPLE_8            = 4
BME280_OSAMPLE_16           = 5

# Standby Settings
BME280_STANDBY_0P5          = 0
BME280_STANDBY_62P5         = 1
BME280_STANDBY_125          = 2
BME280_STANDBY_250          = 3
BME280_STANDBY_500          = 4
BME280_STANDBY_1000         = 5
BME280_STANDBY_10           = 6
BME280_STANDBY_20           = 7

# Filter Settings
BME280_FILTER_OFF           = 0
BME280_FILTER_2             = 1
BME280_FILTER_4             = 2
BME280_FILTER_8             = 3
BME280_FILTER_16            = 4

# BME280 Registers
BME280_REGISTER_DIG_T1      = 0x88  # Trimming parameter registers
BME280_REGISTER_DIG_T2      = 0x8a
BME280_REGISTER_DIG_T3      = 0x8c
BME280_REGISTER_DIG_P1      = 0x8e
BME280_REGISTER_DIG_P2      = 0x90
BME280_REGISTER_DIG_P3      = 0x92
BME280_REGISTER_DIG_P4      = 0x94
BME280_REGISTER_DIG_P5      = 0x96
BME280_REGISTER_DIG_P6      = 0x98
BME280_REGISTER_DIG_P7      = 0x9a
BME280_REGISTER_DIG_P8      = 0x9c
BME280_REGISTER_DIG_P9      = 0x9e
BME280_REGISTER_DIG_H1      = 0xa1
BME280_REGISTER_DIG_H2      = 0xe1
BME280_REGISTER_DIG_H3      = 0xe3
BME280_REGISTER_DIG_H4      = 0xe4
BME280_REGISTER_DIG_H5      = 0xe5
BME280_REGISTER_DIG_H6      = 0xe6
BME280_REGISTER_DIG_H7      = 0xe7
BME280_REGISTER_CHIPID      = 0xd0
BME280_REGISTER_VERSION     = 0xd1
BME280_REGISTER_SOFTRESET   = 0xe0
BME280_REGISTER_STATUS      = 0xf3
BME280_REGISTER_CONTROL_HUM = 0xf2
BME280_REGISTER_CONTROL     = 0xf4
BME280_REGISTER_CONFIG      = 0xf5
BME280_REGISTER_DATA        = 0xf7

class BME280(object):
  def __init__(
      self,
      t_mode  = BME280_OSAMPLE_16,
      p_mode  = BME280_OSAMPLE_16,
      h_mode  = BME280_OSAMPLE_16,
      standby = BME280_STANDBY_250,
      filter  = BME280_FILTER_OFF,
      address = BME280_I2CADDR_HI,
      busno = 1):
    # Check that t_mode is valid.
    osample_modes = [BME280_OSAMPLE_1, BME280_OSAMPLE_2, BME280_OSAMPLE_4, BME280_OSAMPLE_8, BME280_OSAMPLE_16]
    standby_modes = [
        BME280_STANDBY_0P5,
        BME280_STANDBY_62P5,
        BME280_STANDBY_125,
        BME280_STANDBY_250,
        BME280_STANDBY_500,
        BME280_STANDBY_1000,
        BME280_STANDBY_10,
        BME280_STANDBY_20]
    filter_modes = [BME280_FILTER_OFF, BME280_FILTER_2, BME280_FILTER_4, BME280_FILTER_8, BME280_FILTER_16]
    if t_mode not in osample_modes:
      raise ValueError(
        'Unexpected t_mode value {0}.'.format(t_mode))
    self._t_mode = t_mode
    # Check that p_mode is valid.
    if p_mode not in osample_modes:
      raise ValueError(
        'Unexpected p_mode value {0}.'.format(p_mode))
    self._p_mode = p_mode
    # Check that h_mode is valid.
    if h_mode not in osample_modes:
      raise ValueError(
        'Unexpected h_mode value {0}.'.format(h_mode))
    self._h_mode = h_mode
    # Check that standby is valid.
    if standby not in standby_modes:
      raise ValueError(
        'Unexpected standby value {0}.'.format(standby))
    self._standby = standby
    # Check that filter is valid.
    if filter not in filter_modes:
      raise ValueError(
        'Unexpected filter value {0}.'.format(filter))
    self._filter = filter
    # Create device
    self._busno = busno
    self._device = SMBus(busno)
    self._address = address
    # Load calibration values.
    self._load_calibration()
    self._write_8(BME280_REGISTER_CONTROL, 0x24)  # Sleep mode
    time.sleep(0.002)
    self._write_8(BME280_REGISTER_CONFIG, ((standby << 5) | (filter << 2)))
    time.sleep(0.002)
    self._write_8(BME280_REGISTER_CONTROL_HUM, h_mode)  # Set Humidity Oversample
    self._write_8(BME280_REGISTER_CONTROL, ((t_mode << 5) | (p_mode << 2) | 3))  # Set Temp/Pressure Oversample and enter Normal mode
    self.t_fine = 0.0

  def _read_u16(self, reg_addr):
    return self._device.read_word_data(self._address, reg_addr)

  def _read_s16(self, reg_addr):
    val = self._read_u16(reg_addr)
    if (val & 0x8000) == 0x8000:
      return val - (1 << 16)
    else:
      return val

  def _read_u8(self, reg_addr):
    return self._device.read_byte_data(self._address, reg_addr)

  def _read_s8(self, reg_addr):
    val = self._read_u8(reg_addr)
    if (val & 0x80) == 0x80:
      return val - (1 << 8)
    else:
      return val

  def _write_8(self, reg_addr, data):
    self._device.write_byte_data(self._address, reg_addr, data)

  def _load_calibration(self):
    self.dig_T1 = self._read_u16(BME280_REGISTER_DIG_T1)
    self.dig_T2 = self._read_s16(BME280_REGISTER_DIG_T2)
    self.dig_T3 = self._read_s16(BME280_REGISTER_DIG_T3)

    self.dig_P1 = self._read_u16(BME280_REGISTER_DIG_P1)
    self.dig_P2 = self._read_s16(BME280_REGISTER_DIG_P2)
    self.dig_P3 = self._read_s16(BME280_REGISTER_DIG_P3)
    self.dig_P4 = self._read_s16(BME280_REGISTER_DIG_P4)
    self.dig_P5 = self._read_s16(BME280_REGISTER_DIG_P5)
    self.dig_P6 = self._read_s16(BME280_REGISTER_DIG_P6)
    self.dig_P7 = self._read_s16(BME280_REGISTER_DIG_P7)
    self.dig_P8 = self._read_s16(BME280_REGISTER_DIG_P8)
    self.dig_P9 = self._read_s16(BME280_REGISTER_DIG_P9)

    self.dig_H1 = self._read_u8(BME280_REGISTER_DIG_H1)
    self.dig_H2 = self._read_s16(BME280_REGISTER_DIG_H2)
    self.dig_H3 = self._read_u8(BME280_REGISTER_DIG_H3)
    self.dig_H6 = self._read_s8(BME280_REGISTER_DIG_H7)

    h4 = self._read_s8(BME280_REGISTER_DIG_H4)
    h4 = (h4 << 4)
    self.dig_H4 = h4 | (self._read_u8(BME280_REGISTER_DIG_H5) & 0x0f)

    h5 = self._read_s8(BME280_REGISTER_DIG_H6)
    h5 = (h5 << 4)
    self.dig_H5 = h5 | (
    self._read_u8(BME280_REGISTER_DIG_H5) >> 4 & 0x0f)

  def read_raw_temp(self):
    """Waits for reading to become available on device."""
    """Does a single burst read of all data values from device."""
    """Returns the raw (uncompensated) temperature from the sensor."""
    # Worst case measurement time: 113 ms
    remaining_time_millis = 150
    while (self._read_u8(BME280_REGISTER_STATUS) & 0x08) and (remaining_time_millis > 0):
      time.sleep(0.01)
      remaining_time_millis -= 10
    if (self._read_u8(BME280_REGISTER_STATUS) & 0x08):
      raise TimeoutError('Sensor measurement timeout')
    self.BME280Data = self._device.read_i2c_block_data(self._address, BME280_REGISTER_DATA, 8)
    raw = ((self.BME280Data[3] << 16) | (self.BME280Data[4] << 8) | self.BME280Data[5]) >> 4
    return raw

  def read_raw_pressure(self):
    """Returns the raw (uncompensated) pressure level from the sensor."""
    """Assumes that the temperature has already been read """
    """i.e. that BME280Data[] has been populated."""
    raw = ((self.BME280Data[0] << 16) | (self.BME280Data[1] << 8) | self.BME280Data[2]) >> 4
    return raw

  def read_raw_humidity(self):
    """Returns the raw (uncompensated) humidity value from the sensor."""
    """Assumes that the temperature has already been read """
    """i.e. that BME280Data[] has been populated."""
    raw = (self.BME280Data[6] << 8) | self.BME280Data[7]
    return raw

  def read_temperature(self):
    """Gets the compensated temperature in degrees celsius."""
    # float in Python is double precision
    UT = float(self.read_raw_temp())
    var1 = (UT / 16384.0 - float(self.dig_T1) / 1024.0) * float(self.dig_T2)
    var2 = ((UT / 131072.0 - float(self.dig_T1) / 8192.0) * (
    UT / 131072.0 - float(self.dig_T1) / 8192.0)) * float(self.dig_T3)
    self.t_fine = int(var1 + var2)
    temp = (var1 + var2) / 5120.0
    return temp

  def read_pressure(self):
    """Gets the compensated pressure in Pascals."""
    adc = float(self.read_raw_pressure())
    var1 = float(self.t_fine) / 2.0 - 64000.0
    var2 = var1 * var1 * float(self.dig_P6) / 32768.0
    var2 = var2 + var1 * float(self.dig_P5) * 2.0
    var2 = var2 / 4.0 + float(self.dig_P4) * 65536.0
    var1 = (
         float(self.dig_P3) * var1 * var1 / 524288.0 + float(self.dig_P2) * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * float(self.dig_P1)
    if var1 == 0:
      return 0
    p = 1048576.0 - adc
    p = ((p - var2 / 4096.0) * 6250.0) / var1
    var1 = float(self.dig_P9) * p * p / 2147483648.0
    var2 = p * float(self.dig_P8) / 32768.0
    p = p + (var1 + var2 + float(self.dig_P7)) / 16.0
    return p

  def read_humidity(self):
    adc = float(self.read_raw_humidity())
    # print 'Raw humidity = {0:d}'.format (adc)
    h = float(self.t_fine) - 76800.0
    h = (adc - (float(self.dig_H4) * 64.0 + float(self.dig_H5) / 16384.0 * h)) * (
    float(self.dig_H2) / 65536.0 * (1.0 + float(self.dig_H6) / 67108864.0 * h * (
    1.0 + float(self.dig_H3) / 67108864.0 * h)))
    h = h * (1.0 - float(self.dig_H1) * h / 524288.0)
    if h > 100:
      h = 100
    elif h < 0:
      h = 0
    return h

  def get_bus(self):
    return self._busno

  def get_address(self):
    return self._address
