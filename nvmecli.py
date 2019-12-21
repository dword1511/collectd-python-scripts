#!/usr/bin/env python

# Get NVME heath status through nvme-cli
# NOTE: assuming just 1 namespace
# Depends on: nvme-cli


import collectd
import os, subprocess
import re, json


def emit_count(vl, a, v):
  vl.dispatch(type = 'count', type_instance = a, values = [v])

def emit_error(vl, a, v):
  vl.dispatch(type = 'disk_error', type_instance = a, values = [v])

def emit_gauge(vl, a, v):
  vl.dispatch(type = 'gauge', type_instance = a, values = [v])

def emit_percentage(vl, a, v):
  vl.dispatch(type = 'percent', type_instance = a, values = [v])

# Will be converted to ops per interval
# NOTE: the 'command' type is relatively new, so not using it
def emit_commands(vl, a, v):
  vl.dispatch(type = 'operations', type_instance = a, values = [v])

# Unit: Kelvin (Celsius + 273.15)
def emit_temperature(vl, a, v):
  vl.dispatch(type = 'temperature', type_instance = a, values = [v - 273])

def emit_duration_seconds(vl, a, v):
  vl.dispatch(type = 'duration', type_instance = a, values = [v])

def emit_duration_minutes(vl, a, v):
  vl.dispatch(type = 'duration', type_instance = a, values = [v * 60])

def emit_uptime_minutes(vl, a, v):
  vl.dispatch(type = 'uptime', type_instance = a, values = [v * 60])

def emit_uptime_hours(vl, a, v):
  vl.dispatch(type = 'uptime', type_instance = a, values = [v * 3600])

# Unit: 1000 * 512, regardless of NVM's LBA size
def emit_bytes(vl, a, v):
  vl.dispatch(type = 'total_bytes', type_instance = a, values = [v * 512000])

# Namespace usage
# Unit: 512, regardless of NVM's LBA size
def emit_df(vl, a, v):
  vl.dispatch(type = 'df_complex', type_instance = a, values = [v * 512])

def process_cmd(vl, dev, cmd):
  properties = {
    # See NVME 1.3b Fig. 93.
    'critical_warning'      : ('Warning Flag'      , emit_gauge           ), # Currently not parsing bit-fields
    'temperature'           : ('Composite'         , emit_temperature     ), # Device composite temperature
    'avail_spare'           : ('Avail Spares'      , emit_percentage      ),
    'spare_thresh'          : ('Spare Limit'       , emit_percentage      ),
    'percent_used'          : ('Used Endurance'    , emit_percentage      ),
    'data_units_read'       : ('Read bps'          , emit_bytes           ),
    'data_units_written'    : ('Write bps'         , emit_bytes           ),
    'host_read_commands'    : ('Read ops'          , emit_commands        ),
    'host_write_commands'   : ('Write ops'         , emit_commands        ),
    'controller_busy_time'  : ('Ctl Busy'          , emit_uptime_minutes  ), # Put it together with power on hours
    'power_cycles'          : ('Power Cycles'      , emit_count           ),
    'power_on_hours'        : ('Total'             , emit_uptime_hours    ),
    'unsafe_shutdowns'      : ('Unsafe Shutdown'   , emit_count           ), # Put it together with power cycles
    'media_errors'          : ('Media Errors'      , emit_error           ), # Uncorrectable events
    'num_err_log_entries'   : ('Error Logs'        , emit_error           ),
    'warning_temp_time'     : ('Warning Temp'      , emit_duration_minutes),
    'critical_comp_time'    : ('Critical Temp'     , emit_duration_minutes),
    'temperature_sensor_1'  : ('Sensor 1'          , emit_temperature     ), # Not always present
    'temperature_sensor_2'  : ('Sensor 2'          , emit_temperature     ), # Not always present
    'temperature_sensor_3'  : ('Sensor 3'          , emit_temperature     ), # Not always present
    'temperature_sensor_4'  : ('Sensor 4'          , emit_temperature     ), # Not always present
    'temperature_sensor_5'  : ('Sensor 5'          , emit_temperature     ), # Not always present
    'temperature_sensor_6'  : ('Sensor 6'          , emit_temperature     ), # Not always present
    'temperature_sensor_7'  : ('Sensor 7'          , emit_temperature     ), # Not always present
    'temperature_sensor_8'  : ('Sensor 8'          , emit_temperature     ), # Not always present
    'thm_temp1_trans_count' : ('Thermal Limit 1'   , emit_error           ),
    'thm_temp2_trans_count' : ('Thermal Limit 2'   , emit_error           ),
    'thm_temp1_total_time'  : ('Thermal Limit 1'   , emit_duration_seconds),
    'thm_temp2_total_time'  : ('Thermal Limit 2'   , emit_duration_seconds),
    'wctemp'                : ('Warning Composite' , emit_temperature     ), # From controller ID
    'cctemp'                : ('Critical Composite', emit_temperature     ), # From controller ID
  }

  out = subprocess.Popen(['nvme', cmd, '-o', 'json', '/dev/' + dev], stdout = subprocess.PIPE).communicate()[0]
  j = json.loads(out)
  # Assuming python 2.x
  for key, val in list(j.items()):
    try:
      a, f = properties[key]
      f(vl, a, val)
    except KeyError as e:
      #print e
      pass

# Slightly different rules here
def process_ns(vl, ns):
  out = subprocess.Popen(['nvme', 'id-ns', '-o', 'json', '/dev/' + ns], stdout = subprocess.PIPE).communicate()[0]
  j = json.loads(out)
  size, cap, used = [j[k] for k in ['nsze', 'ncap', 'nuse']]
  emit_df(vl, 'free', cap - used)
  emit_df(vl, 'used', used)
  emit_df(vl, 'reserved', size - cap)

def read(data = None):
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'nvmecli'

  redev = re.compile('nvme[0-9]+$')
  for dev in os.listdir('/dev'):
    if redev.match(dev):
      vl.plugin_instance = dev
      process_cmd(vl, dev, 'id-ctrl')
      process_cmd(vl, dev, 'smart-log')

  rens = re.compile('nvme[0-9]+n[0-9]+$')
  for ns in os.listdir('/dev'):
    if rens.match(ns):
      vl.plugin_instance = ns
      process_ns(vl, ns)


collectd.register_read(read)
