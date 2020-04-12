# -*- coding: utf-8 -*-

'''
This code is an adaptation of the Arduino_TSL2591 library from
adafruit: https://github.com/adafruit/Adafruit_TSL2591_Library

For configuring I2C on Raspberry Pi
https://learn.adafruit.com/adafruits-raspberry-pi-lesson-4-gpio-setup/configuring-i2c

Datasheet
https://ams.com/en/tsl25911

NOTE on mods:
1. remove unnecessarily functions and rename functions to be less confusing
2. add get gain/integration time multiplier (total gain w.r.t. lowest gain & integration time)
3. discard one ADC sample once timing/gain is set or sensor is enabled (corrects ADC values)
4. Totally manual enable/disable (corrects ADC values)
5. Check integration time/gain values passed
6. Update Lux equation

TODO:
4. lazy-commit for sensor setting / lazy-commit for discarding invalid values?
6. merge AGC functions
'''

import time

from envsensor._smbus2 import SMBus


class TSL2591:

  # *************************************************
  # ******* MACHINE VARIABLES (DO NOT TOUCH) ********
  # *************************************************
  LUX_DF                    = 408.
  LUX_COEFB                 = 1.64  # CH0 coefficient
  LUX_COEFC                 = 0.59  # CH1 coefficient A
  LUX_COEFD                 = 0.86  # CH2 coefficient B

  ADDR                      = 0x29

  COMMAND_NORMAL            = (1 << 7) | (1 << 5)  # Normal register access
  COMMAND_SF                = (1 << 7) | (3 << 5)  # Special functions

  SF_FORCE_IRQ              = 0x04
  SF_CLEAR_ALS              = 0x06
  SF_CLEAR_ALSNP            = 0x07
  SF_CLEAR_NP               = 0x0a

  REGISTER_ENABLE           = 0x00
  REGISTER_CONFIG           = 0x01
  REGISTER_AILTL            = 0x04 # ALS interrupt low threshold low byte
  REGISTER_AILTH            = 0x05 # ALS interrupt low threshold high byte
  REGISTER_AIHTL            = 0x06 # ALS interrupt high threshold low byte
  REGISTER_AIHTH            = 0x07 # ALS interrupt high threshold high byte
  REGISTER_NPAILTL          = 0x08
  REGISTER_NPAILTH          = 0x09
  REGISTER_NPAIHTL          = 0x0a
  REGISTER_NPAIHTH          = 0x0b
  REGISTER_PERSIST          = 0x0c
  REGISTER_PID              = 0x11 # PAckage ID
  REGISTER_ID               = 0x12
  REGISTER_STATUS           = 0x13
  REGISTER_C0DATAL          = 0x14 # Channel 0 (full) low byte
  REGISTER_C0DATAH          = 0x15 # Channel 0 (full) high byte
  REGISTER_C1DATAL          = 0x16 # Channel 1 (IR) low byte
  REGISTER_C1DATAH          = 0x17 # Channel 1 (IR) high byte

  ENABLE_ALLOFF             = 0x00
  ENABLE_PON                = 1 << 0
  ENABLE_AEN                = 1 << 1
  ENABLE_AIEN               = 1 << 4
  ENABLE_SAI                = 1 << 6
  ENABLE_NPIEN              = 1 << 7

  CONTROL_RESET             = 1 << 7

  ID_DEVID                  = 0x50

  STATUS_NPINTR             = 1 << 5
  # *****************************************
  # ******* END OF MACHINE VARIABLES ********
  # *****************************************

  # Integration time
  # The integration time can be set between 100 and 600ms,
  # and the longer the integration time the more light the
  # sensor is able to integrate, making it more sensitive in
  # low light the longer the integration time.
  INTEGRATIONTIME_100MS = 0x00 # shortest integration time (bright light)
  INTEGRATIONTIME_200MS = 0x01
  INTEGRATIONTIME_300MS = 0x02
  INTEGRATIONTIME_400MS = 0x03
  INTEGRATIONTIME_500MS = 0x04
  INTEGRATIONTIME_600MS = 0x05 # longest integration time (dim light)

  # Gain
  # The gain can be set to one of the following values
  # (though the last value, MAX, has limited use in the
  # real world given the extreme amount of gain applied):
  # GAIN_LOW: Sets the gain to 1x (bright light)
  # GAIN_MEDIUM: Sets the gain to 25x (general purpose)
  # GAIN_HIGH: Sets the gain to 428x (low light)
  # GAIN_MAX: Sets the gain to 9876x (extremely low light)
  GAIN_LOW  = 0x00
  GAIN_MED  = 0x10
  GAIN_HIGH = 0x20
  GAIN_MAX  = 0x30

  # 0x9000 - 1 (36863) for 100 ms integration
  # 0x10000 - 1 (16-bit) for all others
  ADC_MAX_100MS   = 36863
  ADC_MAX         = 65535

  # Dicts for relative multipliers for integration time and gains
  MULTIPLIER_TIME = {
    INTEGRATIONTIME_100MS: 1.,
    INTEGRATIONTIME_200MS: 2.,
    INTEGRATIONTIME_300MS: 3.,
    INTEGRATIONTIME_400MS: 4.,
    INTEGRATIONTIME_500MS: 5.,
    INTEGRATIONTIME_600MS: 6.,
  }
  MULTIPLIER_TIME_INV   = {v: k for k, v in MULTIPLIER_TIME.items()}
  MULTIPLIER_TIME_VALS  = sorted(MULTIPLIER_TIME.values(), reverse = True)
  MULTIPLIER_GAIN = {
    GAIN_LOW  : 1.   ,
    GAIN_MED  : 25.  ,
    GAIN_HIGH : 428. ,
    GAIN_MAX  : 9876.,
  }
  MULTIPLIER_GAIN_INV   = {v: k for k, v in MULTIPLIER_GAIN.items()}
  MULTIPLIER_GAIN_VALS  = sorted(MULTIPLIER_GAIN.values(), reverse = True)

  # Maximum multiplier from integrate time and gain
  MULTIPLIER_MAX  = 9876 * 6


  def _check_param(self, integration_time, gain):
    if integration_time not in list(self.MULTIPLIER_TIME.keys()):
      raise ValueError('Invalid integration time')
    if gain             not in list(self.MULTIPLIER_GAIN.keys()):
      raise ValueError('Invalid gain')

  def _verify_id(self):
    devid = self._bus.read_byte_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_ID)
    if devid != self.ID_DEVID:
      raise ValueError('Expect device 0x{:02x}, got 0x{:02x}'.format(self.DEVID, devid))


  def __init__(
    self,
    i2c_bus         = 1,
    sensor_address  = ADDR,
    integration     = INTEGRATIONTIME_200MS,
    gain            = GAIN_MED
  ):
    self._bus_no = i2c_bus
    self._bus = SMBus(i2c_bus)
    self._sensor_address = sensor_address
    self._verify_id()

    self._check_param(integration, gain)
    self._integration_time = integration
    self._gain = gain

    # Initialize sensor settings
    self.set_timing(self._integration_time, False)
    self.set_gain(self._gain, False)
    self._enabled = False


  def __del__(self):
    try:
      self._bus.close()
    except:
      pass


  def get_bus_no(self):
    return self._bus_no


  '''
  def reset(self):
    self._bus.write_byte_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_CONFIG, self.CONTROL_RESET)
    # TODO: initialize settings so they are in sync
  '''


  def set_timing(self, integration, flush = True):
    if flush:
      self.disable()
    self._check_param(integration, self._gain)
    self._integration_time = integration
    self._bus.write_byte_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_CONFIG, self._integration_time | self._gain)
    if flush:
      self.enable()


  def get_timing(self):
    return self._integration_time


  def get_timing_multiplier(self):
    return self.MULTIPLIER_TIME[self._integration_time]


  def set_gain(self, gain, flush = True):
    if flush:
      self.disable()
    self._check_param(self._integration_time, gain)
    self._gain = gain
    self._bus.write_byte_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_CONFIG, self._integration_time | self._gain)
    if flush:
      self.enable()


  def get_gain(self):
    return self._gain


  def get_gain_multiplier(self):
    return self.MULTIPLIER_GAIN[self._gain]


  def get_multiplier(self):
    return self.get_timing_multiplier() * self.get_gain_multiplier()


  def set_multiplier(self, multiplier):
    self.disable()
    multiplier = max(1., multiplier)

    # Determine ATIME and use ATIME to satisfy multiplier first to ensure SNR
    timing = self.INTEGRATIONTIME_100MS
    for m in self.MULTIPLIER_TIME_VALS:
      if multiplier > m:
        timing = self.MULTIPLIER_TIME_INV[m]
        multiplier = multiplier / m
        break

    # Determine analog gain
    gain = self.GAIN_LOW
    for m in self.MULTIPLIER_GAIN_VALS:
      if multiplier > m:
        gain = self.MULTIPLIER_GAIN_INV[m]
        multiplier = multiplier / m
        break

    # Apply and flush incorrect measurement
    self.set_timing(timing, False)
    self.set_gain(gain, False)
    self.enable()


  def get_max_count(self):
    if self._integration_time is self.INTEGRATIONTIME_100MS:
      return self.ADC_MAX_100MS
    else:
      return self.ADC_MAX


  def is_saturated(self, *args, **kwds):
    if len(args) == 1:
      full = args[0]['full']
      ir = args[0]['ir']
    elif len(args) == 2:
      full = args[0]
      ir = args[1]
    else:
      full = kwds['full']
      ir = kwds['ir']

    # NOTE: for 100 ms integration, value can go beyond ADC_MAX_100MS to 37888
    max_count = self.get_max_count()
    return (full >= max_count) or (ir >= max_count)


  '''
  ADC count per Lux: cpl = (ATIME * AGAIN) / DF
  Consider: mlt = ATIME / 100 * AGAIN
  Thus: cpl = (mlt * 100) / LUX_DF

  Original lux calculation (for reference sake)
  lux1 = (full - (LUX_COEFB * ir)) / cpl
  lux2 = ((LUX_COEFC * full) - (LUX_COEFD * ir) / cpl
  lux = max(lux1, lux2)
  (See: https://github.com/adafruit/Adafruit_TSL2591_Library/issues/14)

  Alternative 1:
  lux = (full - ir) * (1 - ir / full) / cpl
  (Essentially full - ir^2 / full?)

  Alternative 2:
  lux = (full - LUX_COEFB * ir) / cpl
  '''
  def calculate_lux(self, *args, **kwargs):
    if len(args) == 1:
      full = args['full']
      ir = args['ir']
    elif len(args) == 2:
      full = args[0]
      ir = args[1]
    else:
      full = kwargs['full']
      ir = kwargs['ir']

    # Check for overflow conditions first
    if self.is_saturated(full, ir):
      return None

    # cpl = (ATIME * AGAIN) / DF
    # (mlt = ATIME / 100 * AGAIN)
    mlt = self.get_multiplier()
    cpl = (mlt * 100) / self.LUX_DF
    lux = (full - self.LUX_COEFB * ir) / cpl

    return lux


  def enable(self):
    self._bus.write_byte_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_ENABLE, self.ENABLE_PON | self.ENABLE_AEN | self.ENABLE_AIEN)
    time.sleep(0.105 + 0.100 * self._integration_time) # TODO: check AINT
    self._enabled = True


  def disable(self):
    self._enabled = False
    self._bus.write_byte_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_ENABLE, self.ENABLE_ALLOFF)


  def get_values(self):
    if not self._enabled:
      self.enable()
    time.sleep(0.105 + 0.100 * self._integration_time) # TODO: check AINT
    full = self._bus.read_word_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_C0DATAL)
    ir   = self._bus.read_word_data(self._sensor_address, self.COMMAND_NORMAL | self.REGISTER_C1DATAL)
    return full, ir


  def get_all(self):
    full, ir = self.get_values()
    lux = self.calculate_lux(full, ir)  # convert raw values to lux
    output = {
      'lux': lux,
      'full': full,
      'ir': ir,
      'gain': self._gain,
      'integration_time': self._integration_time,
      'multiplier': self.get_multiplier(),
      'bus': self._bus_no,
    }

    return output
