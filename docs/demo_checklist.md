# QoS Traffic Management System — D1 Demo Checklist

## 1. Before the Demonstration

- [ ] Verify that the project files are present.
- [ ] Start the Ryu Python virtual environment.
- [ ] Confirm that Open vSwitch is running.
- [ ] Confirm that Mininet is installed and working.
- [ ] Open separate terminals for the controller and Mininet.
- [ ] Keep the sender, receiver, and results files ready.

## 2. Start the SDN Controller

From the project directory:

```fish
cd ~/qos-project
source ryu-env/bin/activate.fish
ryu-manager --ofp-tcp-listen-port 6653 controller/qos_controller.py
```

**Expected result:**
- Ryu starts without errors.
- The controller listens for OpenFlow connections on port 6653.
- The controller is ready to receive switch connections.

## 3. Start the Mininet Topology

In another terminal:

```fish
sudo mn --topo single,2 --mac \
--switch ovsk,protocols=OpenFlow13 \
--controller remote,ip=127.0.0.1,port=6653
```

At the Mininet prompt, run:

```text
pingall
```

**Expected result:**
- Two hosts, h1 and h2, connect through switch s1.
- The controller connects to the switch.
- `pingall` reports successful connectivity.

## 4. Demonstrate Traffic Classification

Generate traffic for each class:

| Traffic class | UDP port | Priority | Queue |
|---|---:|---|---:|
| Voice | 5001 | High | 3 |
| Video | 5002 | Medium | 2 |
| Best effort | 5003 | Low | 1 |

Show the controller terminal and point out the classification messages.

**Expected controller output:**
- HIGH traffic classified on port 5001 and assigned queue 3.
- MEDIUM traffic classified on port 5002 and assigned queue 2.
- LOW traffic classified on port 5003 and assigned queue 1.

## 5. Demonstrate OpenFlow Rules

From the Mininet prompt:

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

Point out the three UDP classification rules.

Verify that the rules contain:
- UDP destination port 5001 with `set_queue:3`.
- UDP destination port 5002 with `set_queue:2`.
- UDP destination port 5003 with `set_queue:1`.

## 6. Demonstrate QoS Queues

Inspect the QoS configuration:

```text
sh ovs-vsctl list Port s1-eth2
```

Inspect queue statistics:

```text
sh ovs-ofctl -O OpenFlow13 queue-stats s1
```

Explain that queue 1 is best effort, queue 2 is video, and queue 3 is voice.

## 7. Demonstrate Traffic Generation and Reception

Start the receiver on h2:

```text
h2 python3 -u /tmp/qos-app/receiver.py --log /tmp/demo_receiver.csv
```

Generate traffic from h1 using the sender application. Use the three traffic classes and their corresponding UDP ports.

Example voice traffic:

```text
h1 python3 -u /tmp/qos-app/sender.py --host 10.0.0.2 --port 5001 --class-name voice --rate 50 --duration 10 --payload-size 256 --log /tmp/demo_voice.csv
```

Repeat with:
- Video: port 5002, class name `video`.
- Best effort: port 5003, class name `best_effort`.

Show the receiver CSV file and explain the recorded packet information.

## 8. Present Experimental Results

Show these files:

- `results/test1/multiport_receiver_test1.csv`
- `results/test2/multiport_receiver_test2_backup.csv`
- `results/comparison_summary.csv`
- `results/graphs/delay_comparison.png`
- `results/graphs/test2_packet_counts.png`
- `results/graphs/test2_throughput.png`

Highlight the higher-load experiment:

| Metric | Voice | Video | Best effort |
|---|---:|---:|---:|
| Packets received | 5,926 | 3,606 | 2,434 |
| Mean apparent delay | 92.461 ms | 195.186 ms | 294.356 ms |
| Payload throughput | 4.85 Mbps | 2.95 Mbps | 1.99 Mbps |

Explain that these are preliminary measurements from the QoS-enabled setup. A controlled QoS-disabled comparison is needed before claiming a measured improvement caused by QoS.

## 9. Member 3 — Contribution Summary

Explain your responsibilities:

1. Integrated UDP traffic classification with the Ryu SDN controller.
2. Implemented OpenFlow rules for the three traffic classes.
3. Mapped traffic classes to the corresponding OVS queues.
4. Verified flow installation using OpenFlow flow statistics.
5. Coordinated traffic-generation and receiver testing.
6. Collected and analyzed packet logs.
7. Prepared result summaries, graphs, and project documentation.

## 10. Known Pending Work

- [ ] Integrate the final topology and controller files shared by Member 1.
- [ ] Run a controlled QoS-enabled versus QoS-disabled experiment.
- [ ] Validate queue behaviour under sustained congestion.
- [ ] Rehearse the complete demonstration with all team members.

## 11. Cleanup After the Demonstration

At the Mininet prompt:

```text
exit
```

Then clean up Mininet:

```fish
sudo mn -c
```

Stop the Ryu controller with `Ctrl + C`.

---

**Demo success criteria:** The controller connects, hosts communicate, all three traffic classes are classified correctly, OpenFlow rules show the correct queue assignments, and receiver logs demonstrate successful packet reception.
