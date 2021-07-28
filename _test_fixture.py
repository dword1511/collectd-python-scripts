#!/usr/bin/env python3
"""Simple test fixture for collectd python plugins.

This fixture fakes a collectd module to test plugins.

Usage: python _test_fixture.py [plugin_name_without_py] <config key> <config value>
Usage: python _test_fixture.py [dir.plugin_name_without_py] <config key> <config value>
"""

import sys


class _collectd:
    """Fake collectd class."""
    @staticmethod
    def _def_config(_=None):
        print('Default config')

    @staticmethod
    def _def_init():
        print('Default init')

    @staticmethod
    def _def_read(_=None):
        print('Default read')

    @staticmethod
    def _def_shutdown():
        print('Default shutdown')

    @staticmethod
    def _def_write():
        print('Default write')

    @staticmethod
    def _def_flush():
        print('Default flush')

    @staticmethod
    def _def_log():
        print('Default log')

    def __init__(self):
        self.f_config = _collectd._def_config
        self.f_init = _collectd._def_init
        self.f_read = _collectd._def_read
        self.f_shutdown = _collectd._def_shutdown
        self.f_write = _collectd._def_write
        self.f_flush = _collectd._def_flush
        self.f_log = _collectd._def_log

    def register_config(self, func):
        self.f_config = func

    def register_init(self, func):
        self.f_init = func

    def register_read(self, func):
        self.f_read = func

    def register_shutdown(self, func):
        self.f_shutdown = func

    def register_write(self, func):
        self.f_write = func

    def register_flush(self, func):
        self.f_flush = func

    def register_log(self, func):
        self.f_log = func

    def unregister_config(self):
        self.f_config = self._def_config

    def unregister_init(self):
        self.f_init = self._def_init

    def unregister_read(self):
        self.f_read = self._def_read

    def unregister_shutdown(self):
        self.f_shutdown = self._def_shutdown

    def unregister_write(self):
        self.f_write = self._def_write

    def unregister_flush(self):
        self.f_flush = self._def_flush

    def unregister_log(self):
        self.f_log = self._def_log

    def error(self, msg):
        print('Plugin Error: ' + str(msg))

    def warning(self, msg):
        print('Plugin Warning: ' + str(msg))

    def notice(self, msg):
        print('Plugin Notice: ' + str(msg))

    def info(self, msg):
        print('Plugin Info: ' + str(msg))

    def debug(self, msg):
        print('Plugin Debug: ' + str(msg))

    class Values:
        def __init__(self, type=None, plugin=None):
            print(f'Values.init: type = {type} plugin = {plugin}')
            self.type = type
            self.plugin_instance = ''
            self.type_instance = ''
            self.plugin = plugin
            self.host = '(default)'
            self.time = 0
            self.interval = 0

        def dispatch(self,
                     values,
                     type=None,
                     plugin_instance=None,
                     type_instance=None,
                     plugin=None,
                     host=None,
                     time=None,
                     interval=None):
            if not isinstance(values, (list, tuple)):
                raise ValueError('values must be list or tuple')
            if type is None:
                type = self.type
            if plugin_instance is None:
                plugin_instance = self.plugin_instance
            if type_instance is None:
                type_instance = self.type_instance
            if plugin is None:
                plugin = self.plugin
            if host is None:
                host = self.host
            if time is None:
                time = self.time
            if interval is None:
                interval = self.interval
            if None in locals():
                raise ValueError('no argument shall be None')
            print(f'Dispatch: '
                  f'type = "{type}"; '
                  f'values = {values}; '
                  f'p_instance = "{plugin_instance}"; '
                  f't_instance = "{type_instance}"; '
                  f'plugin = "{plugin}"; '
                  f'host = "{host}"; '
                  f'time = {time}; '
                  f'interval = {interval}')


class _Config:
    def __init__(self, key=None, values=None, parent=None, children=None):
        self.parent = parent
        self.key = key
        self.values = values
        self.children = children


def _main():
    argc = len(sys.argv)
    if argc < 2 or argc % 2 == 1:
        print(
            f'Usage: {sys.argv[0]} [plugin_name_without_.py] <config key> <config value>'
        )
        sys.exit(1)

    # Parse configs
    configs = dict()
    for i in range(2, argc, 2):
        key = sys.argv[i]
        value = sys.argv[i + 1]
        if value == 'true':
            value = True
        elif value == 'false':
            value = False
        else:
            try:
                value = int(value, 0)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
        configs[key] = (value, )

    # Override system's collectd module, like LD_PRELOAD for python
    collectd = _collectd()
    sys.modules['collectd'] = collectd

    __import__(sys.argv[1], fromlist=['*'])

    if len(configs) != 0:
        print('Configs: ' + str(configs))
        config_root = _Config()
        config_children = (_Config(k, v, config_root)
                           for k, v in configs.items())
        config_root.children = config_children
        print('f_config')
        collectd.f_config(config_root)
    print('f_init')
    collectd.f_init()
    print('f_read')
    collectd.f_read()
    print('f_shutdown')
    collectd.f_shutdown()


if __name__ == '__main__':
    _main()
