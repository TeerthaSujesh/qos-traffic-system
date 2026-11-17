#!/bin/bash

# Start the 4-host QoS project topology
sudo mn --topo single,4 \
  --switch ovsk,protocols=OpenFlow13 \
  --controller remote,ip=127.0.0.1,port=6653
