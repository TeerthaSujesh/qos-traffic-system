# QoS Traffic Management System – D2

## Overview
This project implements a Software Defined Networking (SDN)-based QoS traffic management system using Mininet, UDP socket programming, and an OS-Ken controller.

D2 extends the D1 setup to support multiple clients communicating with multiple servers.

## D2 Topology

- 3 clients: h1, h2, h3
- 2 servers: h4, h5
- 1 Open vSwitch switch: s1

| Host | Role | IP Address |
|---|---|---|
| h1 | Client 1 | 10.0.0.1 |
| h2 | Client 2 | 10.0.0.2 |
| h3 | Client 3 | 10.0.0.3 |
| h4 | Server 1 | 10.0.0.4 |
| h5 | Server 2 | 10.0.0.5 |


## Running the D2 Topology

Start the OS-Ken controller in a separate terminal:

    source ~/osken-env/bin/activate
    cd ~/CampusCompute/CampusCompute/qos-traffic-system
    osken-manager qos_controller.py

Start the topology in another terminal:

    sudo python3 d2_topology.py

At the Mininet prompt, verify connectivity using pingall.

## Starting the Servers

    h4 python3 receiver.py --host 0.0.0.0 --log logs/d2/server1_received.csv &
    h5 python3 receiver.py --host 0.0.0.0 --log logs/d2/server2_received.csv &

## Performance Analysis

Run from the project root:

    python experiments/analyze_d2.py
    python experiments/analyze_congestion.py

## Concurrent Experiment Results

| Traffic Class | Sent | Received | Estimated Loss | Average Delay |
|---|---:|---:|---:|---:|
| Voice | 500 | 500 | 0.00% | 0.807 ms |
| Video | 800 | 800 | 0.00% | 0.657 ms |
| Best Effort | 1000 | 1000 | 0.00% | 0.652 ms |

## Congestion Experiment Results

| Traffic Class | Sent | Received | Estimated Loss | Average Delay |
|---|---:|---:|---:|---:|
| Voice | 1500 | 643 | 57.13% | 230.538 ms |
| Best Effort | 2250 | 595 | 73.56% | 230.513 ms |

A 100 Kbit/s bottleneck was present on s1-eth4. Queue statistics are saved in results/d2/congestion_qdisc_stats.txt. Queue drops are interface-level statistics, not per-class measurements.

## Measurement Notes

- Delay is apparent one-way delay calculated from sender and receiver timestamps.
- Jitter is the mean absolute deviation of received interarrival times.
- Estimated loss compares sender and receiver records for the same session.
- A static-versus-dynamic QoS comparison requires separately verified results from both configurations.

## Project Files

- d2_topology.py: D2 Mininet topology.
- sender.py and receiver.py: UDP traffic generation and reception.
- qos_controller.py: OS-Ken controller.
- experiments/: performance analysis scripts.
- logs/d2/: sender and receiver CSV logs.
- results/d2/: metrics, graphs, and queue statistics.
