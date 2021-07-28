"""Monitors NVME heath status through nvme-cli.

NOTE: assuming 1 namespace per device
Depends on: nvme-cli
"""

import json
import os
import re
import subprocess

import collectd


def emit_count(values, label, data):
    """Dispatches count data."""
    values.dispatch(type='count', type_instance=label, values=[data])


def emit_error(values, label, data):
    """Dispatches error counts data."""
    values.dispatch(type='disk_error', type_instance=label, values=[data])


def emit_gauge(values, label, data):
    """Dispatches gauge data."""
    values.dispatch(type='gauge', type_instance=label, values=[data])


def emit_percentage(values, label, data):
    """Dispatches percentage data."""
    values.dispatch(type='percent', type_instance=label, values=[data])


def emit_commands(values, label, data):
    """Dispatches ops data.

    Will be converted to ops per interval by collectd/rrd.
    NOTE: the 'command' type is relatively new, so not using it.
    """
    values.dispatch(type='operations', type_instance=label, values=[data])


def emit_temperature(values, label, data):
    """Dispatches temperature data.

    Input unit is Kelvin (Celsius + 273.15).
    """
    values.dispatch(type='temperature',
                    type_instance=label,
                    values=[data - 273])


def emit_duration_seconds(values, label, data):
    """Dispatches duration data in seconds."""
    values.dispatch(type='duration', type_instance=label, values=[data])


def emit_duration_minutes(values, label, data):
    """Dispatches duration data in minutes."""
    values.dispatch(type='duration', type_instance=label, values=[data * 60])


def emit_uptime_minutes(values, label, data):
    """Dispatches uptime data (monotonically increasing) in minutes."""
    values.dispatch(type='uptime', type_instance=label, values=[data * 60])


def emit_uptime_hours(values, label, data):
    """Dispatches uptime data (monotonically increasing) in hours."""
    values.dispatch(type='uptime', type_instance=label, values=[data * 3600])


def emit_bytes(values, label, data):
    """Dispatches byte count data.

    Input unit is always 1000 * 512, regardless of NVM's LBA size.
    """
    values.dispatch(type='total_bytes',
                    type_instance=label,
                    values=[data * 512000])


def emit_df(values, label, data):
    """Dispatches namespace usage data.

    Input unit is always 512, regardless of NVM's LBA size.
    """
    values.dispatch(type='df_complex',
                    type_instance=label,
                    values=[data * 512])


_PROPERTIES = {
    # Each row = key as in JSON: (type instance, handler aka. formatter)
    # See NVME 1.3b Fig. 93.

    # Currently not parsing bit-fields
    'critical_warning': ('Warning Flag', emit_gauge),
    # Device composite temperature
    'temperature': ('Composite', emit_temperature),
    'avail_spare': ('Avail Spares', emit_percentage),
    'spare_thresh': ('Spare Limit', emit_percentage),
    'percent_used': ('Used Endurance', emit_percentage),
    'data_units_read': ('Read bps', emit_bytes),
    'data_units_written': ('Write bps', emit_bytes),
    'host_read_commands': ('Read ops', emit_commands),
    'host_write_commands': ('Write ops', emit_commands),
    # Put this together with power on hours
    'controller_busy_time': ('Ctl Busy', emit_uptime_minutes),
    'power_cycles': ('Power Cycles', emit_count),
    'power_on_hours': ('Total', emit_uptime_hours),
    # Put this together with power cycles
    'unsafe_shutdowns': ('Unsafe Shutdown', emit_count),
    # Uncorrectable events
    'media_errors': ('Media Errors', emit_error),
    'num_err_log_entries': ('Error Logs', emit_error),
    'warning_temp_time': ('Warning Temp', emit_duration_minutes),
    'critical_comp_time': ('Critical Temp', emit_duration_minutes),

    # Additional temperature sensors are not always present
    'temperature_sensor_1': ('Sensor 1', emit_temperature),
    'temperature_sensor_2': ('Sensor 2', emit_temperature),
    'temperature_sensor_3': ('Sensor 3', emit_temperature),
    'temperature_sensor_4': ('Sensor 4', emit_temperature),
    'temperature_sensor_5': ('Sensor 5', emit_temperature),
    'temperature_sensor_6': ('Sensor 6', emit_temperature),
    'temperature_sensor_7': ('Sensor 7', emit_temperature),
    'temperature_sensor_8': ('Sensor 8', emit_temperature),
    'thm_temp1_trans_count': ('Thermal Limit 1', emit_error),
    'thm_temp2_trans_count': ('Thermal Limit 2', emit_error),
    'thm_temp1_total_time': ('Thermal Limit 1', emit_duration_seconds),
    'thm_temp2_total_time': ('Thermal Limit 2', emit_duration_seconds),

    # From controller ID
    'wctemp': ('Warning Composite', emit_temperature),
    'cctemp': ('Critical Composite', emit_temperature),
}


def process_cmd(values, dev, cmd):
    """Processes command output for one drive."""
    out = subprocess.Popen(['nvme', cmd, '-o', 'json', '/dev/' + dev],
                           stdout=subprocess.PIPE).communicate()[0]
    j = json.loads(out)
    for key, val in list(j.items()):
        try:
            label, func = _PROPERTIES[key]
            func(values, label, val)
        except KeyError:
            collectd.debug(f'Skipping unknown field {key}')


def process_ns(values, namespace):
    """Processes namespace command output for one drive."""
    out = subprocess.Popen(
        ['nvme', 'id-ns', '-o', 'json', '/dev/' + namespace],
        stdout=subprocess.PIPE).communicate()[0]
    j = json.loads(out)
    size, cap, used = map(j.get, ['nsze', 'ncap', 'nuse'])
    emit_df(values, 'free', cap - used)
    emit_df(values, 'used', used)
    emit_df(values, 'reserved', size - cap)


def read(_=None):
    values = collectd.Values(plugin='nvmecli')

    redev = re.compile('nvme[0-9]+$')
    for dev in os.listdir('/dev'):
        if redev.match(dev):
            values.plugin_instance = dev
            process_cmd(values, dev, 'id-ctrl')
            process_cmd(values, dev, 'smart-log')

    rens = re.compile('nvme[0-9]+n[0-9]+$')
    for namespace in os.listdir('/dev'):
        if rens.match(namespace):
            values.plugin_instance = namespace
            process_ns(values, namespace)


collectd.register_read(read)
