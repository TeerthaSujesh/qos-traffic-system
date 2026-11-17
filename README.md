# QoS Traffic Management System — D2

## 1. Overview

This project implements an SDN-based Quality of Service (QoS) traffic
management system using Mininet, Open vSwitch (OVS), UDP socket programming,
and an OS-Ken controller.

D2 extends the earlier topology to support multiple clients communicating
with multiple servers. Traffic is classified into voice, video, and
best-effort classes. The controller maps these classes to OVS queues.

## 2. D2 Network Topology

The D2 topology contains three clients, two servers, and one OVS switch.

| Host | Role | IP address |
|---|---|---|
| h1 | Client 1 | 10.0.0.1 |
| h2 | Client 2 | 10.0.0.2 |
| h3 | Client 3 | 10.0.0.3 |
| h4 | Server 1 | 10.0.0.4 |
| h5 | Server 2 | 10.0.0.5 |
| s1 | Open vSwitch | — |

All five hosts connect to switch s1. The controller communicates with OVS
using OpenFlow.

## 3. Traffic Classification and QoS Queues

The UDP receiver ports identify the traffic classes:

| UDP port | Traffic class | OVS queue | Priority |
|---|---|---:|---|
| 5001 | Voice | 3 | High |
| 5002 | Video | 2 | Medium |
| 5003 | Best effort | 1 | Low |

The controller installs flow rules that set the corresponding queue before
forwarding packets to the destination server.

The congestion experiment used Linux HTB QoS on the server1-facing switch
port, s1-eth4:

| Queue | Traffic class | Configured minimum rate |
|---:|---|---:|
| 1 | Best effort | 100 Kbit/s |
| 2 | Video | 250 Kbit/s |
| 3 | Voice | 500 Kbit/s |

The configured port maximum rate was 1 Mbit/s. These are static queue
settings; this experiment does not demonstrate dynamic QoS adaptation.

## 4. Requirements

The tested environment used:

- Ubuntu under WSL
- Mininet 2.3.0
- Open vSwitch 3.7.1
- OS-Ken 3.1.1
- Python 3
- pandas and matplotlib

Install the system packages:

    sudo apt update
    sudo apt install -y mininet openvswitch-switch python3-venv

Create and prepare the project analysis environment:

    cd ~/qos-traffic-system
    python3 -m venv .venv
    source .venv/bin/activate
    pip install pandas matplotlib

OS-Ken is run from its separate environment:

    source ~/osken-env/bin/activate

## 5. Running the D2 Experiment

Use separate terminals.

### Terminal 1 — Start the controller

    cd ~/qos-traffic-system
    source ~/osken-env/bin/activate
    osken-manager qos_controller.py

### Terminal 2 — Start the Mininet topology

    cd ~/qos-traffic-system
    sudo python3 d2_topology.py

At the Mininet prompt, verify connectivity:

    pingall

The completed test had 0% packet loss in the topology connectivity check.

### Start the receivers

At the Mininet prompt, run:

    h4 python3 receiver.py --host 0.0.0.0 --log logs/d2/server1_received.csv &
    h5 python3 receiver.py --host 0.0.0.0 --log logs/d2/server2_received.csv &

### Run the baseline traffic test

At the Mininet prompt, start the three clients:

    h1 python3 sender.py --host 10.0.0.5 --port 5001 --class-name voice --rate 20 --duration 15 --log logs/d2/client1_voice.csv &
    h2 python3 sender.py --host 10.0.0.4 --port 5002 --class-name video --rate 20 --duration 15 --log logs/d2/client2_video.csv &
    h3 python3 sender.py --host 10.0.0.5 --port 5003 --class-name best_effort --rate 20 --duration 15 --log logs/d2/client3_best_effort.csv &

The completed baseline run sent and received 300 packets for each class.

## 6. Congestion and QoS Experiment

The congestion test applied HTB queue configuration to the egress port
connected to server h4. Run this at the Mininet prompt after starting the
topology:

    sh ovs-vsctl -- set Port s1-eth4 qos=@qos -- --id=@qos create QoS type=linux-htb other-config:max-rate=1000000 queues:1=@q1 queues:2=@q2 queues:3=@q3 -- --id=@q1 create Queue other-config:min-rate=100000 other-config:max-rate=1000000 -- --id=@q2 create Queue other-config:min-rate=250000 other-config:max-rate=1000000 -- --id=@q3 create Queue other-config:min-rate=500000 other-config:max-rate=1000000

For the recorded congestion run, the receiver and two senders were:

    h4 python3 receiver.py --host 0.0.0.0 --log logs/d2/congestion_server1_received.csv &
    h1 python3 sender.py --host 10.0.0.4 --port 5001 --class-name voice --rate 500 --duration 10 --payload-size 1200 --log logs/d2/congestion_client1.csv &
    h3 python3 sender.py --host 10.0.0.4 --port 5003 --class-name best_effort --rate 500 --duration 10 --payload-size 1200 --log logs/d2/congestion_client3.csv &

The recorded congestion test compared voice and best-effort traffic.
Video was tested in the baseline experiment, not in this congestion run.

Useful verification commands at the Mininet prompt:

    sh ovs-vsctl list qos
    sh ovs-ofctl -O OpenFlow13 dump-flows s1
    sh tc -s class show dev s1-eth4

## 7. Performance Analysis

From a normal project terminal, activate the analysis environment:

    cd ~/qos-traffic-system
    source .venv/bin/activate

Run the analysis scripts:

    python experiments/analyze_d2.py
    python experiments/analyze_congestion.py

The scripts read the CSV logs in logs/d2/ and generate metric CSV files
and comparison graphs in results/d2/.

## 8. Recorded Results

### Baseline concurrent traffic

| Traffic class | Sent | Received | Estimated loss | Average delay | Average jitter | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| Voice | 300 | 300 | 0.00% | 0.455 ms | 0.190 ms | 41.10 Kbps |
| Video | 300 | 300 | 0.00% | 0.373 ms | 0.125 ms | 41.10 Kbps |
| Best effort | 300 | 300 | 0.00% | 0.337 ms | 0.116 ms | 41.10 Kbps |

All three traffic classes were delivered successfully in this baseline
run. This establishes multi-client/multi-server communication but does not,
by itself, establish prioritization under congestion.

### Voice versus best-effort congestion test

| Traffic class | Sent | Received | Estimated loss | Average delay | Average jitter | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| Voice | 965 | 965 | 0.00% | 763.678 ms | 3.984 ms | 854.20 Kbps |
| Best effort | 476 | 435 | 8.61% | 1632.151 ms | 20.234 ms | 409.65 Kbps |

In this recorded run, voice had approximately 53% lower average delay and
80% lower average jitter than best-effort traffic. Voice had no observed
packet loss in its sender/receiver logs, while best effort had an estimated
8.61% loss.

The OpenFlow flow counters confirmed that voice traffic to UDP port 5001
was assigned queue 3 and best-effort traffic to UDP port 5003 was assigned
queue 1. HTB class counters also showed traffic in the corresponding
classes. These observations are consistent with preferential treatment
for voice traffic under the tested congestion conditions.

## 9. Measurement Definitions and Limitations

- Packets sent are counted from sender CSV records marked as sent.
- Packets received are counted from matching receiver records for the
  sender session.
- Estimated packet loss is calculated from sender and receiver record
  counts for the same session.
- Apparent one-way delay is calculated from sender and receiver timestamps.
  Both applications ran within the same Mininet/WSL environment.
- Jitter is calculated as the mean absolute deviation of received
  interarrival intervals. It is not an RTP jitter measurement.
- Throughput is calculated from received payload bytes over the observed
  receive interval.
- The congestion loss figure is application-observed estimated loss; it
  should not be interpreted as a direct count of HTB queue drops.
- The requested sender rate is a configuration value. Actual packet counts
  in the congestion run differed between senders, so the results should be
  interpreted using the recorded counts and measured metrics.
- The results represent the tested topology and traffic conditions; they
  are not a guarantee of identical performance under other workloads.

## 10. Project Files

- `sender.py` — UDP traffic generator.
- `receiver.py` — UDP traffic receiver and measurement logger.
- `qos_controller.py` — OS-Ken controller and traffic-to-queue rules.
- `qos_topology.py` — existing D1 topology.
- `d2_topology.py` — D2 multi-client/multi-server topology.
- `experiments/analyze_d2.py` — baseline metrics and graphs.
- `experiments/analyze_congestion.py` — congestion metrics and graphs.
- `logs/d2/` — sender and receiver CSV evidence.
- `results/d2/` — generated metric CSV files and graphs.

The D1 topology and existing application/controller files are retained.
