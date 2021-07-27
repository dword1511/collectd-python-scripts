"""Fail2ban jail state fetcher for collectd.
Based on fail2ban-client code.
Authors:
  Antti Jaakkola <annttu@annttu.fi>
  Chi Zhang <zhangchi866@gmail.com>

Fail2Ban is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

Fail2Ban is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Fail2Ban; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import socket
import collectd

from fail2ban.client.csocket import CSocket
from fail2ban.client.configurator import Configurator


class Fail2banClient:
    """Basic Fail2ban socket client for fetching jail status."""
    def __init__(self, conf_dir="/etc/fail2ban"):
        self._configurator = Configurator()
        self._configurator.setBaseDir(conf_dir)
        self._configurator.readEarly()
        self._socket = self._configurator.getEarlyOptions()["socket"]
        collectd.info("Using socket file " + self._socket)

    def _process_cmd(self, jail="", listjails=False):
        cmds = []
        if listjails:
            cmds.append(['status'])
        elif jail:
            cmds.append(['status', jail])
        for cmd in cmds:
            try:
                client = CSocket(self._socket)
                ret = client.send(cmd)
                if ret[0] == 0:
                    if not listjails:
                        retval = ret[1][1][1][0][1]
                    else:
                        retval = [i.strip() for i in ret[1][1][1].split(",")]
                    return retval
                else:
                    collectd.warning("NOK: " + repr(ret[1].args) + " -> " +
                                     ret[1])
                    return None
            except socket.error:
                collectd.error("Unable to contact server. Is it running?")
                return None
            except Exception as err:
                collectd.error(err)
                return None

    def get_banned(self, jail):
        """Returns number of banned hosts for the given jail."""
        return self._process_cmd(jail)

    def list_jails(self):
        """Returns a list of active jails."""
        return self._process_cmd(listjails=True)


_CLIENT = None


def init():
    global _CLIENT
    _CLIENT = Fail2banClient()
    return True


def read(_=None):
    global _CLIENT
    # NOTE: consider creating client everytime since config might change
    values = collectd.Values(type='gauge', plugin='fail2ban')
    for jail in _CLIENT.list_jails():
        values.dispatch(type_instance=jail, values=[_CLIENT.get_banned(jail)])


collectd.register_read(read)
collectd.register_init(init)
