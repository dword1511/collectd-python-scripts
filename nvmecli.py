#!/usr/bin/env python

# Get NVME heath status through nvme-cli
# NOTE: assuming just 1 namespace
# Depends on: nvme-cli


import collectd
import os, subprocess
import re, json


# TODO: consider 'smart_powercycles'
def emit_count(vl, a, v):
  vl.dispatch(type = 'count', type_instance = a, values = [v])

# TODO: consider 'smart_badsectors'
def emit_error(vl, a, v):
  vl.dispatch(type = 'disk_error', type_instance = a, values = [v])

def emit_gauge(vl, a, v):
  vl.dispatch(type = 'gauge', type_instance = a, values = [v])

def emit_percentage(vl, a, v):
  vl.dispatch(type = 'percent', type_instance = a, values = [v])

# Will be converted to ops per interval
# NOTE: the 'command' type is relatively new
def emit_commands(vl, a, v):
  vl.dispatch(type = 'operations', type_instance = a, values = [v])

# Unit: Kelvin (Celsius + 273.15)
# TODO: consider 'smart_temperature'
def emit_temperature(vl, a, v):
  vl.dispatch(type = 'temperature', type_instance = a, values = [v - 273])

def emit_duration_seconds(vl, a, v):
  vl.dispatch(type = 'duration', type_instance = a, values = [v])

def emit_duration_minutes(vl, a, v):
  vl.dispatch(type = 'duration', type_instance = a, values = [v * 60])

# TODO: consider 'smart_poweron'
def emit_uptime_minutes(vl, a, v):
  vl.dispatch(type = 'uptime', type_instance = a, values = [v * 60])

# TODO: consider 'smart_poweron'
def emit_uptime_hours(vl, a, v):
  vl.dispatch(type = 'uptime', type_instance = a, values = [v * 3600])

# Unit: 1000 * 512, regardless of NVM's LBA size
# TODO: 'disk_octets' type require read and write at the same time
def emit_bytes(vl, a, v):
  vl.dispatch(type = 'total_bytes', type_instance = a, values = [v * 512000])


def read(data = None):
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'nvmecli'

  redev = re.compile('nvme[0-9]+$')
  funcs = {
    # See NVME 1.3b Fig. 93.
    'critical_warning'      : emit_gauge,           # Currently not parsing bit-fields
    'temperature'           : emit_temperature,     # Device composite temperature
    'avail_spare'           : emit_percentage,
    'spare_thresh'          : emit_percentage,
    'percent_used'          : emit_percentage,      # Used endurance
    'data_units_read'       : emit_bytes,
    'data_units_written'    : emit_bytes,
    'host_read_commands'    : emit_commands,        # Too large to be drawn with other counts
    'host_write_commands'   : emit_commands,        # Too large to be drawn with other counts
    'controller_busy_time'  : emit_uptime_minutes,  # Put it together with power on hours
    'power_cycles'          : emit_count,
    'power_on_hours'        : emit_uptime_hours,
    'unsafe_shutdowns'      : emit_count,           # Put it together with power cycles
    'media_errors'          : emit_error,           # Uncorrectable events
    'num_err_log_entries'   : emit_error,
    'warning_temp_time'     : emit_duration_minutes,
    'critical_comp_time'    : emit_duration_minutes,
    'temperature_sensor_1'  : emit_temperature,     # Not always present
    'temperature_sensor_2'  : emit_temperature,     # Not always present
    'temperature_sensor_3'  : emit_temperature,     # Not always present
    'temperature_sensor_4'  : emit_temperature,     # Not always present
    'temperature_sensor_5'  : emit_temperature,     # Not always present
    'temperature_sensor_6'  : emit_temperature,     # Not always present
    'temperature_sensor_7'  : emit_temperature,     # Not always present
    'temperature_sensor_8'  : emit_temperature,     # Not always present
    'thm_temp1_trans_count' : emit_error,
    'thm_temp2_trans_count' : emit_error,
    'thm_temp1_total_time'  : emit_duration_seconds,
    'thm_temp2_total_time'  : emit_duration_seconds,
  }
  names = {
    'critical_warning'      : 'Warning Flag',
    'temperature'           : 'Composite',
    'avail_spare'           : 'Avail Spares',
    'spare_thresh'          : 'Spare Limit',
    'percent_used'          : 'Used Endurance',
    'data_units_read'       : 'Read bps',
    'data_units_written'    : 'Write bps',
    'host_read_commands'    : 'Read ops',
    'host_write_commands'   : 'Write ops',
    'controller_busy_time'  : 'Ctl Busy',
    'power_cycles'          : 'Power Cycles',
    'power_on_hours'        : 'Total',
    'unsafe_shutdowns'      : 'Unsafe Shutdown',
    'media_errors'          : 'Media Errors',
    'num_err_log_entries'   : 'Error Logs',
    'warning_temp_time'     : 'Warning Temp',
    'critical_comp_time'    : 'Critical Temp',
    'temperature_sensor_1'  : 'Sensor 1',
    'temperature_sensor_2'  : 'Sensor 2',
    'temperature_sensor_3'  : 'Sensor 3',
    'temperature_sensor_4'  : 'Sensor 4',
    'temperature_sensor_5'  : 'Sensor 5',
    'temperature_sensor_6'  : 'Sensor 6',
    'temperature_sensor_7'  : 'Sensor 7',
    'temperature_sensor_8'  : 'Sensor 8',
    'thm_temp1_trans_count' : 'Thermal Limit 1',
    'thm_temp2_trans_count' : 'Thermal Limit 2',
    'thm_temp1_total_time'  : 'Thermal Limit 1',
    'thm_temp2_total_time'  : 'Thermal Limit 2',
  }

  for dev in os.listdir('/dev'):
    if redev.match(dev):
      vl.plugin_instance = dev
      out = subprocess.Popen(['nvme', 'smart-log', '-o', 'json', '/dev/' + dev], stdout = subprocess.PIPE).communicate()[0]
      j = json.loads(out)
      # Assuming python 2.x
      for key, val in j.iteritems():
        a = names[key]
        f = funcs[key]
        if a is not None and f is not None:
          f(vl, a, val)


collectd.register_read(read)
