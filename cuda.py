#!/usr/bin/env python

# Monitors NVIDIA graphic cards via NVIDIA SMI
# Origin: https://github.com/sajkec/cuda-collectd
# Origin: https://github.com/bgamari/cuda-collectd
# Depends on: nvidia-smi

import collectd
import subprocess
import socket
import xml.etree.ElementTree as ET

def configure_callback(conf):
  collectd.info('Configured with')

def read(data = None):
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'cuda'
  vl.host = socket.gethostname()

  out = subprocess.Popen(['nvidia-smi', '-q', '-x'], stdout = subprocess.PIPE).communicate()[0]
  root = ET.fromstring(out)

  for gpu in root.iter('gpu'):
    # GPU id
    vl.plugin_instance = 'gpu-%s' % (gpu.find('minor_number').text)

    # Ignore exception since certain information may not be available on all platforms.
    # GPU fan speed percentage
    try:
      vl.dispatch(type = 'fanspeed', values = [float(gpu.find('fan_speed').text.split()[0])])
    except ValueError:
      pass

    # GPU temperature
    try:
      vl.dispatch(type = 'temperature', values = [float(gpu.find('temperature/gpu_temp').text.split()[0])])
    except ValueError:
      pass

    # GPU power draw
    try:
      vl.dispatch(type = 'power', values = [float(gpu.find('power_readings/power_draw').text.split()[0])])
    except ValueError:
      pass

    # GPU utilization
    try:
      vl.dispatch(type = 'percent', type_instance = 'gpu', values = [float(gpu.find('utilization/gpu_util').text.split()[0])])
    except ValueError:
      pass

    # GPU encoder utilization
    try:
      vl.dispatch(type = 'percent', type_instance = 'encoder', values = [float(gpu.find('utilization/encoder_util').text.split()[0])])
    except ValueError:
      pass

    # GPU decoder utilization
    try:
      vl.dispatch(type = 'percent', type_instance = 'decoder', values = [float(gpu.find('utilization/decoder_util').text.split()[0])])
    except ValueError:
      pass

    # GPU memory utilization
    try:
      vl.dispatch(type = 'percent', type_instance = 'memory', values = [float(gpu.find('utilization/memory_util').text.split()[0])])
    except ValueError:
      pass

    # GPU memory usage
    try:
      vl.dispatch(type = 'memory', type_instance = 'used', values = [1e6 * float(gpu.find('fb_memory_usage/used').text.split()[0])])
    except ValueError:
      pass

    # GPU total memory
    try:
      vl.dispatch(type = 'memory', type_instance = 'total', values = [1e6 * float(gpu.find('fb_memory_usage/total').text.split()[0])])
    except ValueError:
      pass

    # GPU frequency
    try:
      vl.dispatch(type = 'frequency', type_instance = 'gpu', values = [1e6 * float(gpu.find('clocks/graphics_clock').text.split()[0])])
    except ValueError:
      pass

    # GPU memory frequency
    try:
      vl.dispatch(type = 'frequency', type_instance = 'memory', values = [1e6 * float(gpu.find('clocks/mem_clock').text.split()[0])])
    except ValueError:
      pass

    # GPU stream multiprocessor frequency
    try:
      vl.dispatch(type = 'frequency', type_instance = 'stream_mp', values = [1e6 * float(gpu.find('clocks/sm_clock').text.split()[0])])
    except ValueError:
      pass

    # GPU video frequency
    try:
      vl.dispatch(type = 'frequency', type_instance = 'video', values = [1e6 * float(gpu.find('clocks/video_clock').text.split()[0])])
    except ValueError:
      pass

    # GPU application frequency
    try:
      vl.dispatch(type = 'frequency', type_instance = 'app_gpu', values = [1e6 * float(gpu.find('applications_clocks/graphics_clock').text.split()[0])])
    except ValueError:
      pass

    # GPU application memory frequency
    try:
      vl.dispatch(type = 'frequency', type_instance = 'app_memory', values = [1e6 * float(gpu.find('applications_clocks/mem_clock').text.split()[0])])
    except ValueError:
      pass

collectd.register_config(configure_callback)
collectd.register_read(read)
