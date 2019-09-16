# -*- coding: utf-8 -*-

'''
This code is an adaptation of the Arduino_TSL2591 library from
adafruit: https://github.com/adafruit/Adafruit_TSL2591_Library

For configuring I2C on Raspberry Pi
https://learn.adafruit.com/adafruits-raspberry-pi-lesson-4-gpio-setup/configuring-i2c

Datasheet
https://learn.adafruit.com/adafruit-tsl2591/downloads
'''
from __future__ import print_function

import time
import json
from smbus2 import SMBus

# *************************************************
# ******* MACHINE VARIABLES (DO NOT TOUCH) ********
# *************************************************
VISIBLE = 2  # channel 0 - channel 1
INFRARED = 1  # channel 1
FULLSPECTRUM = 0  # channel 0

ADDR = 0x29
READBIT = 0x01
COMMAND_BIT = 0xA0  # bits 7 and 5 for 'command normal'
CLEAR_BIT = 0x40  # Clears any pending interrupt (write 1 to clear)
WORD_BIT = 0x20  # 1 = read/write word (rather than byte)
BLOCK_BIT = 0x10  # 1 = using block read/write
ENABLE_POWERON = 0x01
ENABLE_POWEROFF = 0x00
ENABLE_AEN = 0x02
ENABLE_AIEN = 0x10
CONTROL_RESET = 0x80
LUX_DF = 408.0
LUX_COEFB = 1.64  # CH0 coefficient
LUX_COEFC = 0.59  # CH1 coefficient A
LUX_COEFD = 0.86  # CH2 coefficient B

REGISTER_ENABLE = 0x00
REGISTER_CONTROL = 0x01
REGISTER_THRESHHOLDL_LOW = 0x02
REGISTER_THRESHHOLDL_HIGH = 0x03
REGISTER_THRESHHOLDH_LOW = 0x04
REGISTER_THRESHHOLDH_HIGH = 0x05
REGISTER_INTERRUPT = 0x06
REGISTER_CRC = 0x08
REGISTER_ID = 0x0A
REGISTER_CHAN0_LOW = 0x14
REGISTER_CHAN0_HIGH = 0x15
REGISTER_CHAN1_LOW = 0x16
REGISTER_CHAN1_HIGH = 0x17
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
GAIN_LOW = 0x00
GAIN_MED = 0x10
GAIN_HIGH = 0x20
GAIN_MAX = 0x30


class tsl2591(object):
    '''
    An object class containing a series of methods to enable easy
    interaction with the sensor.
    '''

    def __init__(
            self,
            i2c_bus=1,
            sensor_address=ADDR,
            integration=INTEGRATIONTIME_200MS,
            gain=GAIN_MED
    ):
        self.bus = SMBus(i2c_bus)
        self.sender_address = sensor_address
        self.integration_time = integration
        self.gain = gain
        self.set_timing(self.integration_time)
        self.set_gain(self.gain)
        self.disable()  # to be sure

    def set_timing(self, integration):
        self.enable()
        self.integration_time = integration
        self.bus.write_byte_data(
            self.sender_address,
            COMMAND_BIT | REGISTER_CONTROL,
            self.integration_time | self.gain
        )
        self.disable()

    def get_timing(self):
        return self.integration_time

    def set_gain(self, gain):
        self.enable()
        self.gain = gain
        self.bus.write_byte_data(
            self.sender_address,
            COMMAND_BIT | REGISTER_CONTROL,
            self.integration_time | self.gain
        )
        self.disable()

    def get_gain(self):
        return self.gain

    def calculate_lux(self, full, ir):
        # Check for overflow conditions first
        if (full == 0xFFFF) | (ir == 0xFFFF):
            return 0

        case_integ = {
            INTEGRATIONTIME_100MS: 100.,
            INTEGRATIONTIME_200MS: 200.,
            INTEGRATIONTIME_300MS: 300.,
            INTEGRATIONTIME_400MS: 400.,
            INTEGRATIONTIME_500MS: 500.,
            INTEGRATIONTIME_600MS: 600.,
        }
        if self.integration_time in case_integ.keys():
            atime = case_integ[self.integration_time]
        else:
            atime = 100.

        case_gain = {
            GAIN_LOW: 1.,
            GAIN_MED: 25.,
            GAIN_HIGH: 428.,
            GAIN_MAX: 9876.,
        }

        if self.gain in case_gain.keys():
            again = case_gain[self.gain]
        else:
            again = 1.

        # cpl = (ATIME * AGAIN) / DF
        cpl = (atime * again) / LUX_DF
        lux1 = (full - (LUX_COEFB * ir)) / cpl

        lux2 = ((LUX_COEFC * full) - (LUX_COEFD * ir)) / cpl

        # The highest value is the approximate lux equivalent
        return max([lux1, lux2])

    def enable(self):
        self.bus.write_byte_data(
            self.sender_address,
            COMMAND_BIT | REGISTER_ENABLE,
            ENABLE_POWERON | ENABLE_AEN | ENABLE_AIEN
        )  # Enable

    def disable(self):
        self.bus.write_byte_data(
            self.sender_address,
            COMMAND_BIT | REGISTER_ENABLE,
            ENABLE_POWEROFF
        )

    def get_full_luminosity(self):
        self.enable()
        # not sure if we need it "// Wait x ms for ADC to complete"
        time.sleep(0.105+0.100*self.integration_time)
        full = self.bus.read_word_data(
            self.sender_address, COMMAND_BIT | REGISTER_CHAN0_LOW
        )
        ir = self.bus.read_word_data(
            self.sender_address, COMMAND_BIT | REGISTER_CHAN1_LOW
        )
        self.disable()
        return full, ir

    def get_luminosity(self, channel):
        full, ir = self.get_full_luminosity()
        if channel == FULLSPECTRUM:
            # Reads two byte value from channel 0 (visible + infrared)
            return full
        elif channel == INFRARED:
            # Reads two byte value from channel 1 (infrared)
            return ir
        elif channel == VISIBLE:
            # Reads all and subtracts out ir to give just the visible!
            return full - ir
        else:  # unknown channel!
            return 0

    def get_current(self, format=''):
        full, ir = self.get_full_luminosity()
        lux = self.calculate_lux(full, ir)  # convert raw values to lux
        output = {
            'lux': lux,
            'full': full,
            'ir': ir,
            'gain': self.get_gain(),
            'integration_time': self.get_timing()
        }
        if format == 'json':
            return json.dumps(output)
        return output

    def test(self, int_time=INTEGRATIONTIME_100MS, gain=GAIN_LOW):
        self.set_gain(gain)
        self.set_timing(int_time)
        full_test, ir_test = self.get_full_luminosity()
        lux_test = self.calculate_lux(full_test, ir_test)
        print('Lux = {0:f}  full = {1}  ir = {2}'.format(
            lux_test, full_test, ir_test))
        print('Integration time = {}'.format(self.get_timing()))
        print('Gain = {} \n'.format(self.get_gain()))
