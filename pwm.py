"""Monitors hwmon fan PWM duty cycle.

Duty shows how hard the fans are trying to work.
Useful if hardware or software automatic fan speed control is available.
"""

import os
import re

import collectd

_SYSFS_PWM_DIR = '/sys/class/hwmon'


def _get_hwmon_name(hwmon):
    """Returns a stable name for the hwmon device."""
    with open(f'{_SYSFS_PWM_DIR}/{hwmon}/name') as name_file:
        name = name_file.read()
    device_path = f'{_SYSFS_PWM_DIR}/{hwmon}/device'
    if os.path.islink(device_path):
        name = f'{name}_{os.path.basename(os.readlink(device_path))}'
    return name.strip()


def read(_=None):
    values = collectd.Values(type='fanspeed', plugin='pwm')
    reobj = re.compile('^pwm[0-9]+$')

    for hwmon in os.listdir(_SYSFS_PWM_DIR):
        try:
            values.plugin_instance = _get_hwmon_name(hwmon)
        except OSError as err:
            collectd.warning(
                f'Cannot get name of {hwmon}, use raw name instead: {err}')
            values.plugin_instance = hwmon
        for filename in os.listdir(f'{_SYSFS_PWM_DIR}/{hwmon}'):
            if reobj.match(filename):
                try:
                    with open(f'{_SYSFS_PWM_DIR}/{hwmon}/{filename}'
                              ) as pwm_file:
                        # TODO: resolve PWM name by fan*_label
                        values.dispatch(type_instance=filename,
                                        values=[int(pwm_file.read())])
                except (OSError, ValueError) as err:
                    collectd.error(err)


collectd.register_read(read)
