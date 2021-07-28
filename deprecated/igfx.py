"""Monitors Intel integrated graphics.

Depends on: intel-gpu-tools
WARNING: DANGER: intel-gpu-tools may irreversibly hang your integrated graphics!
(i915 reset won't be able to recorver)
"""

import re
import subprocess

import collectd


# "intel_perf_counters" (too detailed? Also not working on kabylake-r or newer. Not implemented now)
# "intel_gpu_top -s 100 -o -"
# "intel_gpu_frequency -g" or "/sys/class/drm/card%d/gt_cur_freq_mhz".
# See also: https://bwidawsk.net/blog/index.php/2015/05/a-bit-on-intel-gpu-frequency/
# NOTE: GPU ops and invocations are per second values
# NOTE: On newer kernels this may need modifying the kernel.perf_event_paranoid sysctl setting.
#       See: https://unix.stackexchange.com/a/14256/177804
def read(_=None):
    values = collectd.Values(plugin='igfx')

    out = subprocess.Popen(['intel_gpu_frequency', '-g'],
                           stdout=subprocess.PIPE).communicate()[0]
    for line in out.split(b'\n'):
        if "cur" in line:
            values.dispatch(type='frequency',
                            type_instance='gpu',
                            values=[1e6 * float(line.split()[1])])

    proc = subprocess.Popen(['intel_gpu_top', '-s', '100', '-o', '-'],
                            stdout=subprocess.PIPE)
    col = []
    proc.stdout.readline()
    col = re.sub(' +', ' ', proc.stdout.readline()).split()
    proc.terminate()
    if col[0] == '#' or col[0] == '' or len(col) != 18:
        collectd.error(f'Wrong number of columns: {col}')
        return

    # Unavailable statistics are marked with -1.
    # col[0] is timestamp, we can ignore it.

    # col[1] is render busy %
    n = float(col[1])
    if n >= 0:
        values.dispatch(type='percent', type_instance='render', values=[n])

    # col[2] is render ops
    #n = float(col[2])
    #if n >= 0:
    #  values.dispatch(type = 'operations_per_second', type_instance = 'render', values = [n])

    # col[3] is bitstream 0 busy %
    n = float(col[3])
    if n >= 0:
        values.dispatch(type='percent', type_instance='bitstream0', values=[n])

    # col[4] is bitstream 0 ops
    #n = float(col[4])
    #if n >= 0:
    #  values.dispatch(type = 'operations_per_second', type_instance = 'bitstream0', values = [n])

    # col[5] is bitstream 1 busy %
    n = float(col[5])
    if n >= 0:
        values.dispatch(type='percent', type_instance='bitstream1', values=[n])

    # col[6] is bitstream 1 ops
    #n = float(col[6])
    #if n >= 0:
    #  values.dispatch(type = 'operations_per_second', type_instance = 'bitstream1', values = [n])

    # col[7] is blitter busy %
    n = float(col[7])
    if n >= 0:
        values.dispatch(type='percent', type_instance='blitter', values=[n])

    # col[8] is blitter ops
    #n = float(col[8])
    #if n >= 0:
    #  values.dispatch(type = 'operations_per_second', type_instance = 'blitter', values = [n])

    # NOTE: intel_gpu_top has integer overflow for the following fields:
    # col[9] is vertices fetch
    #n = float(col[9])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'operations_per_second', type_instance = 'vertices_fetch', values = [n])

    # col[10] is primitives fetch
    #n = float(col[10])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'operations_per_second', type_instance = 'primitives_fetch', values = [n])

    # col[11] is vertex shader invocations
    #n = float(col[11])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'operations_per_second', type_instance = 'vertex_shader', values = [n])

    # col[12] is geometry shader invocations
    #n = float(col[12])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'operations_per_second', type_instance = 'geometry_shader', values = [n])

    # col[13] is geometry shader primitives
    #n = float(col[13])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'count', type_instance = 'geometry_shader_primitives', values = [n])

    # col[14] is clipper invocations
    #n = float(col[14])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'operations_per_second', type_instance = 'clipper', values = [n])

    # col[15] is clipper primitives
    #n = float(col[15])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'count', type_instance = 'clipper_primitives', values = [n])

    # col[16] is pixel shader invocations
    #n = float(col[16])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'operations_per_second', type_instance = 'pixel_shader', values = [n])

    # col[17] is pixel shader depth passes
    #n = float(col[17])
    #if n >= 0:
    #  if n > pow(2, 63):
    #    n = 0
    #  values.dispatch(type = 'count', type_instance = 'pixel_shader_depth_pass', values = [n])


collectd.register_read(read)
