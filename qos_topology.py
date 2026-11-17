#!/usr/bin/env python3
from mininet.net import Mininet
from mininet.topo import SingleSwitchTopo
from mininet.node import OVSSwitch, Controller
from mininet.cli import CLI
from mininet.log import setLogLevel

def main():
    topo = SingleSwitchTopo(k=4)
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        controller=None,
        autoSetMacs=True
    )

    c0 = net.addController(
        'c0',
        controller=Controller,
        ip='127.0.0.1',
        port=6653
    )

    net.start()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    main()
