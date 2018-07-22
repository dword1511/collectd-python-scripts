#!/usr/bin/env python

# Monitors integrated graphic processor in Intel CPUs
# Depends on: intel-gpu-tools

import collectd
import subprocess
import socket
import time
import re

def configure_callback(conf):
  collectd.info('Configured with')

# "intel_perf_counters" (too detailed? not implemented now)
# "intel_gpu_top -s 100 -o -"
# "intel_gpu_frequency -g" or "/sys/class/drm/card%d/gt_cur_freq_mhz".
# See also: https://bwidawsk.net/blog/index.php/2015/05/a-bit-on-intel-gpu-frequency/
# NOTE: GPU ops and invocations are per second values, where collectd expects total "invocations" and "operations" (DERIVE type).
# Although they fit the semantics, collectd will not handle them properly, esp. when they come to 0.
def read(data = None):
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'igfx'

  out = subprocess.Popen(['intel_gpu_frequency', '-g'], stdout = subprocess.PIPE).communicate()[0]
  for line in out.split('\n'):
    if "cur" in line:
      vl.dispatch(type = 'frequency', type_instance = 'gpu', values = [1e6 * float(line.split()[1])])

  p = subprocess.Popen(['intel_gpu_top', '-s', '100', '-o', '-'], stdout = subprocess.PIPE)
  retries = 3
  col = []
  while True:
    col = re.sub(' +', ' ', p.stdout.readline()).split()
    if col[0] != '#' and col[0] != '' and len(col) == 18:
      break
    time.sleep(1)
    retries = retries - 1
    if retries == 0:
      p.kill()
      raise TimeoutError
  p.terminate()

  # Unavailable statistics are marked with -1.
  # col[0] is timestamp, we can ignore it.

  # col[1] is render busy %
  n = float(col[1])
  if n >= 0:
    vl.dispatch(type = 'percent', type_instance = 'render', values = [n])

  # col[2] is render ops
  n = float(col[2])
  if n >= 0:
    vl.dispatch(type = 'operations_per_second', type_instance = 'render', values = [n])

  # col[3] is bitstream 0 busy %
  n = float(col[3])
  if n >= 0:
    vl.dispatch(type = 'percent', type_instance = 'bitstream0', values = [n])

  # col[4] is bitstream 0 ops
  n = float(col[4])
  if n >= 0:
    vl.dispatch(type = 'operations_per_second', type_instance = 'bitstream0', values = [n])

  # col[5] is bitstream 1 busy %
  n = float(col[5])
  if n >= 0:
    vl.dispatch(type = 'percent', type_instance = 'bitstream1', values = [n])

  # col[6] is bitstream 1 ops
  n = float(col[6])
  if n >= 0:
    vl.dispatch(type = 'operations_per_second', type_instance = 'bitstream1', values = [n])

  # col[7] is blitter busy %
  n = float(col[7])
  if n >= 0:
    vl.dispatch(type = 'percent', type_instance = 'blitter', values = [n])

  # col[8] is blitter ops
  n = float(col[8])
  if n >= 0:
    vl.dispatch(type = 'operations_per_second', type_instance = 'blitter', values = [n])

  # NOTE: intel_gpu_top has integer overflow for the following fields:
  # col[9] is vertices fetch
  n = float(col[9])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'operations_per_second', type_instance = 'vertices_fetch', values = [n])

  # col[10] is primitives fetch
  n = float(col[10])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'operations_per_second', type_instance = 'primitives_fetch', values = [n])

  # col[11] is vertex shader invocations
  n = float(col[11])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'operations_per_second', type_instance = 'vertex_shader', values = [n])

  # col[12] is geometry shader invocations
  n = float(col[12])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'operations_per_second', type_instance = 'geometry_shader', values = [n])

  # col[13] is geometry shader primitives
  n = float(col[13])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'count', type_instance = 'geometry_shader_primitives', values = [n])

  # col[14] is clipper invocations
  n = float(col[14])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'operations_per_second', type_instance = 'clipper', values = [n])

  # col[15] is clipper primitives
  n = float(col[15])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'count', type_instance = 'clipper_primitives', values = [n])

  # col[16] is pixel shader invocations
  n = float(col[16])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'operations_per_second', type_instance = 'pixel_shader', values = [n])

  # col[17] is pixel shader depth passes
  n = float(col[17])
  if n >= 0:
    if n > pow(2, 63):
      n = 0
    vl.dispatch(type = 'count', type_instance = 'pixel_shader_depth_pass', values = [n])

collectd.register_config(configure_callback)
collectd.register_read(read)
