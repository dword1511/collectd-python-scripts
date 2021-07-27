"""Monitors backlight brightness from collectd"""

import os
import sys
import traceback

import collectd

_SYSFS_BL_DIR = '/sys/class/backlight/'


def read(_=None):
    values = collectd.Values(type='percent', plugin='backlight')

    for backlight in os.listdir(_SYSFS_BL_DIR):
        try:
            # "brightness" may differ from "actual_brightness" especially when lid is closed.
            with open(_SYSFS_BL_DIR + backlight +
                      '/actual_brightness') as sysfs_value:
                bl_now = float(sysfs_value.read())
            with open(_SYSFS_BL_DIR + backlight +
                      '/max_brightness') as sysfs_value:
                bl_max = float(sysfs_value.read())
            values.dispatch(type_instance=backlight,
                            values=[bl_now / bl_max * 100])
        except OSError:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            collectd.warning(
                repr(
                    traceback.format_exception(exc_type, exc_value,
                                               exc_traceback)))


collectd.register_read(read)
