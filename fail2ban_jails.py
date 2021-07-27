# Fail2ban jail state fetcher for collectd
# Based on fail2ban-client code
# Author:
#   Antti Jaakkola <annttu@annttu.fi>
#   Chi Zhang <zhangchi866@gmail.com>
#
# Fail2Ban is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Fail2Ban is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Fail2Ban; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import sys, os
import socket
import collectd

from fail2ban.client.csocket import CSocket
from fail2ban.client.configurator import Configurator

class Fail2banClient:
    def __init__(self, conf_dir="/etc/fail2ban"):
        self._configurator = Configurator()
        self._configurator.setBaseDir(conf_dir)
        self._configurator.readEarly()
        self._socket = self._configurator.getEarlyOptions()["socket"]
        collectd.info("Using socket file " + self._socket)

    def _processCmd(self, jail="", listjails=False):
        cmd = []
        if listjails:
            cmd.append(['status'])
        elif jail:
            cmd.append(['status', jail])
        for c in cmd:
            try:
                client = CSocket(self._socket)
                ret = client.send(c)
                if ret[0] == 0:
                    if not listjails:
                        retval = ret[1][1][1][0][1]
                    else:
                        retval = [i.strip() for i in ret[1][1][1].split(",")]
                    return retval
                else:
                    warning("NOK: " + repr(ret[1].args) + " -> " + ret[1])
                    return
            except socket.error:
                collectd.error("Unable to contact server. Is it running?")
                return
            except Exception as e:
                collectd.error(e)
                return

    def get_banned(self, jail):
        return self._processCmd(jail)

    def list_jails(self):
        return self._processCmd(listjails = True)

_client = None
def init():
    global _client
    _client = Fail2banClient()
    return True

def read(data=None):
    global _client
    # NOTE: consider creating client everytime since config might change
    v1 = collectd.Values(type='gauge', plugin='fail2ban')
    for jail in _client.list_jails():
        v1.dispatch(type_instance=jail, values=[_client.get_banned(jail)])

collectd.register_read(read)
collectd.register_init(init)

