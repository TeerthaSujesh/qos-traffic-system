#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.node import OVSSwitch, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel


class D2Topo(Topo):
    def build(self):
        switch = self.addSwitch('s1')

        # Three clients
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')

        # Two servers
        h4 = self.addHost('h4')
        h5 = self.addHost('h5')

        # Connect all hosts to the switch
        for host in [h1, h2, h3, h4, h5]:
            self.addLink(host, switch)


def main():
    topo = D2Topo()

    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        controller=None,
        autoSetMacs=True
    )

    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6653
    )

    net.start()

    print("\nD2 topology started: 3 clients and 2 servers.")
    CLI(net)

    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    main()
