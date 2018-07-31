#!/usr/bin/env python

# Get NVME heath status through nvme-cli
# NOTE: assuming just 1 namespace

import collectd
import os, subprocess
import re, json


def emit_count(vl, a, v):
  vl.dispatch(type = 'count', type_instance = a, values = [v])

def emit_gauge(vl, a, v):
  vl.dispatch(type = 'gauge', type_instance = a, values = [v])

def emit_percentage(vl, a, v):
  vl.dispatch(type = 'percent', type_instance = a, values = [v])

def emit_temperature(vl, a, v):
  vl.dispatch(type = 'temperature', type_instance = a, values = [v])

def emit_time_seconds(vl, a, v):
  vl.dispatch(type = 'duration', type_instance = a, values = [v])

def emit_time_minutes(vl, a, v):
  vl.dispatch(type = 'duration', type_instance = a, values = [v * 60])

def emit_time_hours(vl, a, v):
  vl.dispatch(type = 'uptime', type_instance = a, values = [v * 3600])

def emit_bytes(vl, a, v):
  vl.dispatch(type = 'bytes', type_instance = a, values = [v * 512000])


def read(data = None):
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'nvmecli'

  redev = re.compile('nvme[0-9]+$')
  funcs = {
    # See NVME 1.3b Fig. 93.
    'critical_warning'      : emit_gauge,         # Currently not parsing bit-fields
    'temperature'           : emit_temperature,   # Device composite temperature
    'avail_spare'           : emit_percentage,
    'spare_thresh'          : emit_percentage,
    'percent_used'          : emit_percentage,    # Used endurance
    'data_units_read'       : emit_bytes,
    'data_units_written'    : emit_bytes,
    'host_read_commands'    : emit_count,
    'host_write_commands'   : emit_count,
    'controller_busy_time'  : emit_time_minutes,
    'power_cycles'          : emit_count,
    'power_on_hours'        : emit_time_hours,
    'unsafe_shutdowns'      : emit_count,
    'media_errors'          : emit_count,         # Uncorrectable events
    'num_err_log_entries'   : emit_count,
    'warning_temp_time'     : emit_time_minutes,
    'critical_comp_time'    : emit_time_minutes,
    'temperature_sensor_1'  : emit_temperature,   # Not always present
    'temperature_sensor_2'  : emit_temperature,   # Not always present
    'temperature_sensor_3'  : emit_temperature,   # Not always present
    'temperature_sensor_4'  : emit_temperature,   # Not always present
    'temperature_sensor_5'  : emit_temperature,   # Not always present
    'temperature_sensor_6'  : emit_temperature,   # Not always present
    'temperature_sensor_7'  : emit_temperature,   # Not always present
    'temperature_sensor_8'  : emit_temperature,   # Not always present
    'thm_temp1_trans_count' : emit_count,
    'thm_temp2_trans_count' : emit_count,
    'thm_temp1_total_time'  : emit_time_seconds,
    'thm_temp2_total_time'  : emit_time_seconds,
  }
  names = {
    'critical_warning'      : 'Critical Warning',
    'temperature'           : 'Composite',
    'avail_spare'           : 'Available Spares',
    'spare_thresh'          : 'Spare Threshold',
    'percent_used'          : 'Used Endurance',
    'data_units_read'       : 'Total Read',
    'data_units_written'    : 'Total Written',
    'host_read_commands'    : 'Read Commands',
    'host_write_commands'   : 'Write Commands',
    'controller_busy_time'  : 'Busy Time',
    'power_cycles'          : 'Power Cycles',
    'power_on_hours'        : 'Power On',
    'unsafe_shutdowns'      : 'Unsafe Shutdown',
    'media_errors'          : 'Media Errors',
    'num_err_log_entries'   : 'Error Logs',
    'warning_temp_time'     : 'Warning Temperature',
    'critical_comp_time'    : 'Critical Temperature',
    'temperature_sensor_1'  : 'Sensor 1',
    'temperature_sensor_2'  : 'Sensor 2',
    'temperature_sensor_3'  : 'Sensor 3',
    'temperature_sensor_4'  : 'Sensor 4',
    'temperature_sensor_5'  : 'Sensor 5',
    'temperature_sensor_6'  : 'Sensor 6',
    'temperature_sensor_7'  : 'Sensor 7',
    'temperature_sensor_8'  : 'Sensor 8',
    'thm_temp1_trans_count' : 'Thermal Throttle 1',
    'thm_temp2_trans_count' : 'Thermal Throttle 2',
    'thm_temp1_total_time'  : 'Thermal Throttle 1',
    'thm_temp2_total_time'  : 'Thermal Throttle 2',
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
