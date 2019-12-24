#!/usr/bin/env python

# Monitors NVIDIA graphic cards via NVIDIA SMI
# Based on https://github.com/sajkec/cuda-collectd & https://github.com/bgamari/cuda-collectd
# Depends on: nvidia-smi

import collectd
import subprocess
import xml.etree.ElementTree as ET


def dispatch(vl, tree, path, type, instance = None, multiplier = 1.):
  # Ignore exceptions since values may not be available on all platformss
  try:
    vl.dispatch(type = type, type_instance = instance, values = [multiplier * float(tree.find(path).text.split()[0])])
  except (ValueError, AttributeError) as e:
    #print(path + ': ' + str(e))
    pass

def dispatch_aggregate(vl, tree, path, type, multiplier = 1.):
  # Ignore exceptions since values may not be available on all platformss
  try:
    vl.dispatch(type = type, type_instance = vl.plugin_instance, plugin_instance = '', values = [multiplier * float(tree.find(path).text.split()[0])])
  except (ValueError, AttributeError) as e:
    #print(path + ': ' + str(e))
    pass

def dispatch_state(vl, tree, path, instance):
  # Ignore exceptions since values may not be available on all platformss
  try:
    text = tree.find(path).text.split()[0][1:]
    vl.dispatch(type = 'gauge', type_instance = instance, values = [int(text)])
  except (ValueError, AttributeError) as e:
    #print(path + ': ' + str(e))
    #print(text)
    pass

def dispatch_proc_stat(vl, tree):
  try:
    procs = tree.find('processes')

    n_procs = len(procs)
    vl.dispatch(type = 'users', type_instance = 'Procs', values = [n_procs])

    proc_mem = 0
    for proc in procs:
      proc_mem = proc_mem + float(proc.find('used_memory').text.split()[0]) * (2. ** 20)
    vl.dispatch(type = 'bytes', type_instance = vl.plugin_instance, plugin_instance = '', values = [proc_mem])

  except (ValueError, AttributeError) as e:
    #print(path + ': ' + str(e))
    pass

def read(data = None):
  properties = [
    # Each row = [path, type, instance, multiplier]
    # PCIe traffic in KB/s
    ['pci/tx_util'                        , 'bitrate'              , 'PCIe TX'     , 1.e3    ],
    ['pci/rx_util'                        , 'bitrate'              , 'PCIe RX'     , 1.e3    ],
    # Fan PWM (use aggregate...)
    #['fan_speed'                          , 'fanspeed'   , 'PWM'         , 1.      ],
    # NOTE: performance_state needs special handling (strip the prefixing "P")
    # VRAM usage in MiB
    ['fb_memory_usage/used'               , 'memory'               , 'Used'        , 2. ** 20],
    ['fb_memory_usage/free'               , 'memory'               , 'Free'        , 2. ** 20],
    # CPU-mapped memory TODO: subtract BAR1 from total VRAM, or make a seperate graph/instance
    ['bar1_memory_usage/used'             , 'memory'               , 'BAR1 Used'   , 2. ** 20],
    ['bar1_memory_usage/free'             , 'memory'               , 'BAR1 Free'   , 2. ** 20],
    # Utilization in % (i.e. how busy things are, esp. for memory)
    ['utilization/gpu_util'               , 'percent'              , 'GPU'         , 1.      ],
    ['utilization/encoder_util'           , 'percent'              , 'Encoder'     , 1.      ],
    ['utilization/decoder_util'           , 'percent'              , 'Decoder'     , 1.      ],
    ['utilization/memory_util'            , 'percent'              , 'Memory'      , 1.      ],
    # Encoder sessions, FPS, latency (s)
    ['encoder_stats/session_count'        , 'users'                , 'Encoder'     , 1.      ],
    ['encoder_stats/average_fps'          , 'operations_per_second', 'Encoder'     , 1.      ],
    ['encoder_stats/average_latency'      , 'latency'              , 'Encoder'     , 1.      ],
    # FBC sessions, FPS, latency (s)
    ['fbc_stats/session_count'            , 'users'                , 'FBC'         , 1.      ],
    ['fbc_stats/average_fps'              , 'operations_per_second', 'FBC'         , 1.      ],
    ['fbc_stats/average_latency'          , 'latency'              , 'FBC'         , 1.      ],
    # TODO: ECC errors
    # TODO: retired pages
    # Temperature readings in Celsius
    ['temperature/gpu_temp'               , 'temperature'          , 'GPU'         , 1.      ],
    ['temperature/gpu_temp_max_threshold' , 'temperature'          , 'GPU Max'     , 1.      ],
    ['temperature/gpu_temp_slow_threshold', 'temperature'          , 'GPU Slow'    , 1.      ],
    ['temperature/memory_temp'            , 'temperature'          , 'Memory'      , 1.      ],
    # Power readings in W (NOTE: power_state needs same handling as performance_state)
    ['power_readings/power_draw'          , 'power'                , 'Usage'       , 1.      ],
    ['power_readings/enforced_power_limit', 'power'                , 'Limit'       , 1.      ],
    ['power_readings/min_power_limit'     , 'power'                , 'Limit Min'   , 1.      ],
    ['power_readings/max_power_limit'     , 'power'                , 'Limit Max'   , 1.      ],
    # Clock frequency in MHz
    ['clocks/graphics_clock'              , 'frequency'            , 'Graphics'    , 1.e6    ],
    ['clocks/mem_clock'                   , 'frequency'            , 'Memory'      , 1.e6    ],
    ['clocks/sm_clock'                    , 'frequency'            , 'Stream MP'   , 1.e6    ],
    ['clocks/video_clock'                 , 'frequency'            , 'Video'       , 1.e6    ],
    # Application clock frequency in MHz
    ['applications_clocks/graphics_clock' , 'frequency'            , 'App Graphics', 1.e6    ],
    ['applications_clocks/mem_clock'      , 'frequency'            , 'App Memory'  , 1.e6    ],
    # TODO: max clocks & max custom clocks
    # NOTE: number of processes needs special handling
  ]

  properties_state = [
    ['performance_state'                                 , 'Perf State'            ],
    ['power_readings/power_state'                        , 'Power State'           ],
  ]
  vl = collectd.Values(type = 'gauge')
  vl.plugin = 'cuda'

  out = subprocess.Popen(['nvidia-smi', '-q', '-x'], stdout = subprocess.PIPE).communicate()[0]
  try:
    root = ET.fromstring(out)
  except ET.ParseError as err:
    print("Cannot parse nvidia-smi output: {0}".format(err))
    return

  for gpu in root.iter('gpu'):
    vl.plugin_instance = gpu.attrib['id']
    for path, type, instance, multiplier in properties:
      dispatch(vl, gpu, path, type, instance, multiplier)
    for path, instance in properties_state:
      dispatch_state(vl, gpu, path, instance)
    # Use the same graph for aggregates since they have only one curve per card
    dispatch_aggregate(vl, gpu, 'fan_speed', 'fanspeed')
    dispatch_proc_stat(vl, gpu)

collectd.register_read(read)
