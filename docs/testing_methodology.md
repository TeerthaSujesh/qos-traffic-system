# QoS Traffic Management System — Testing Methodology

## 1. Objective
To evaluate a QoS-based traffic management system that classifies network traffic into three priority classes and assigns each class to a dedicated Open vSwitch queue.

## 2. Traffic Classification

| Traffic class | Application | UDP port | Priority | OVS queue |
|---|---|---:|---:|---:|
| HIGH | Voice | 5001 | 300 | 3 |
| MEDIUM | Video | 5002 | 200 | 2 |
| LOW | Best effort | 5003 | 100 | 1 |

## 3. Experimental Setup
- Operating system: CachyOS Linux
- SDN controller: Ryu
- Switching: Open vSwitch
- Emulator: Mininet
- Protocol: OpenFlow 1.3
- Topology: One switch connecting two hosts
- Sender: Python UDP traffic generator
- Receiver: Python multi-port UDP receiver

## 4. QoS Queue Configuration

| Queue | Traffic class | Minimum rate | Maximum rate |
|---|---|---:|---:|
| 1 | LOW | 1 Mbps | 2 Mbps |
| 2 | MEDIUM | 2 Mbps | 3 Mbps |
| 3 | HIGH | 3 Mbps | 5 Mbps |

Parent port maximum rate: 10 Mbps.

## 5. Test 1 — Low Traffic Load

Concurrent UDP traffic was generated for 10 seconds:
- Voice: 50 packets/second
- Video: 30 packets/second
- Best effort: 20 packets/second
- Payload size: 256 bytes

All 1,000 generated packets were received in the recorded test, with no observed packet loss.

## 6. Test 2 — Higher Traffic Load

Concurrent UDP traffic was generated for 10 seconds:
- Voice: 600 packets/second target
- Video: 500 packets/second target
- Best effort: 500 packets/second target
- Payload size: 1,024 bytes

All 11,966 recorded data packets were received, with no missing or duplicate sequence numbers in the analysis.

## 7. Preliminary Results

| Metric | HIGH | MEDIUM | LOW |
|---|---:|---:|---:|
| Test 2 packets received | 5,926 | 3,606 | 2,434 |
| Mean apparent delay | 92.461 ms | 195.186 ms | 294.356 ms |
| Payload throughput | 4.85 Mbps | 2.95 Mbps | 1.99 Mbps |

HIGH traffic showed the lowest mean apparent delay in Test 2.

## 8. Metrics Collected
- Packets received
- Packet sequence numbers
- Packet loss and duplicates
- Apparent one-way delay
- Interarrival time
- Payload throughput
- Open vSwitch queue packet and byte counters

## 9. Evidence

Raw CSV logs:
- results/test1/
- results/test2/

Graphs:
- results/graphs/

Comparison summary:
- results/comparison_summary.csv

## 10. Pending Final Validation

The preliminary tests verify traffic classification, queue assignment and packet delivery. A controlled comparison with QoS disabled and enabled under identical offered traffic is still required to establish the QoS performance benefit.

Final integration with the team's shared topology and controller files is also pending.
