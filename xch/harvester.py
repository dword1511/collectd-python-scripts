"""Monitors Chia harvesters.

Depends on: pygtail
"""

import os
import re
import tempfile

import collectd

from pygtail.core import Pygtail

_PATTERN_PLOT_INFO = re.compile(
    r'Loaded a total of ([0-9]+) plots of size ([0-9]+\.[0-9]+) TiB, '
    r'in ([0-9]+\.[0-9]+) seconds')

# Although we can get a more up-to-date plot count here, we won't be able to
# update total plot size.
_PATTERN_PROOF_INFO = re.compile(
    r'([0-9]+) plots were eligible for farming ([0-9a-f]+)... '
    r'Found ([0-9]+) proofs. '
    r'Time: ([0-9]+\.[0-9]+) s. ')

_last_plot_count = 0
_last_plot_size_tib = 0.
_last_plot_scan_time = 0.
_last_plot_scan_time_max = 0.

_last_proof_time = []

_log_dir = None
_log = None


def _update_last_plot_info(lines):
    global _last_plot_count, _last_plot_size_tib, _last_plot_scan_time, _last_plot_scan_time_max

    for line in lines:
        plot_info_matches = _PATTERN_PLOT_INFO.search(line)
        if plot_info_matches:
            _last_plot_count = int(plot_info_matches.group(1))
            _last_plot_size_tib = float(plot_info_matches.group(2))
            _last_plot_scan_time = float(plot_info_matches.group(3))
            _last_plot_scan_time_max = max(_last_plot_scan_time_max,
                                           _last_plot_scan_time)


def config(config_in):
    """Parses additional config.

    Config example:

    Import "xch.harvester"
    <Module "xch.harvester">
      LogDir "/home/somebody/.chia/mainnet/log/"
    </Module>
    """
    global _log_dir

    for node in config_in.children:
        key = node.key.lower()
        val = node.values

        if key == 'LogDir'.lower():
            assert len(val) == 1
            _log_dir = val[0]
        else:
            collectd.warning('Skipping unknown config key "{}"'.format(key))


def init():
    """Opens log files for read.

    Pygtail can handle rotated logs (debug.log.[0-9]) from chia.
    """
    global _log

    if not _log_dir:
        raise RuntimeError('LogDir must be specified')

    log_path = f'{_log_dir}/debug.log'
    file_desc, offset_path = tempfile.mkstemp(prefix='collectd_xch_harvester',
                                              suffix='offset')
    os.close(file_desc)
    _log = Pygtail(filename=log_path, offset_file=offset_path)
    _update_last_plot_info(_log.readlines())

    return True


def read(_=None):
    global _last_plot_scan_time_max, _last_proof_time

    values = collectd.Values(plugin='xch', plugin_instance='harvester')

    lines = _log.readlines()

    _update_last_plot_info(lines)
    try:
        values.dispatch(type='gauge',
                        type_instance='Plot',
                        values=[_last_plot_count])
        values.dispatch(type='bytes',
                        type_instance='Total plot size',
                        values=[round(_last_plot_size_tib * (1024**4))])
        values.dispatch(type='duration',
                        type_instance='Plot scan last',
                        values=[_last_plot_scan_time])
        # _last_plot_scan_time_max would be 0 if no plot scan happend during
        # this period of time
        values.dispatch(
            type='duration',
            type_instance='Plot scan max',
            values=[max(_last_plot_scan_time_max, _last_plot_scan_time)])
        _last_plot_scan_time_max = 0.
    except ValueError as err:
        collectd.error(err)

    eligible_plot_count = 0
    blocks = set()
    proof_count = 0
    proof_time = []
    for line in lines:
        proof_info_matches = _PATTERN_PROOF_INFO.search(line)
        if proof_info_matches:
            try:
                eligible_plot_count += int(proof_info_matches.group(1))
            except ValueError as err:
                collectd.error(err)

            blocks.add(proof_info_matches.group(2))

            try:
                proof_count += int(proof_info_matches.group(3))
            except ValueError as err:
                collectd.error(err)

            try:
                proof_time.append(float(proof_info_matches.group(4)))
            except ValueError as err:
                collectd.error(err)

    values.dispatch(type='gauge',
                    type_instance='Eligible plot',
                    values=[eligible_plot_count])
    values.dispatch(type='gauge', type_instance='Block', values=[len(blocks)])
    values.dispatch(type='gauge', type_instance='Proof', values=[proof_count])

    # NOTE: data may get distorted by RRD interpolation. Max proof duration usually appears somewhat
    # lower than actual due to its spiky nature. To workaround, save min and max proof times and use
    # them twice.
    if proof_time:
        values.dispatch(type='duration',
                        type_instance='Proof average',
                        values=[sum(proof_time) / len(proof_time)])
        values.dispatch(type='duration',
                        type_instance='Proof min',
                        values=[min(proof_time + _last_proof_time)])
        values.dispatch(type='duration',
                        type_instance='Proof max',
                        values=[max(proof_time + _last_proof_time)])
    _last_proof_time = proof_time


collectd.register_config(config)
collectd.register_init(init)
collectd.register_read(read)
