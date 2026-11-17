import argparse
import csv
import json
import os
import select
import socket
import time

VERSION = 1
TRAFFIC_CLASSES = {"voice", "video", "best_effort"}
DEFAULT_PORTS = [5001, 5002, 5003]


def new_session():
    return {
        "sequences": set(),
        "received": 0,
        "duplicates": 0,
        "expected": None,
        "delays": [],
        "intervals": [],
        "bytes": 0,
        "first": None,
        "last": None,
        "last_mono": None,
    }


def main():
    parser = argparse.ArgumentParser(description="QoS UDP traffic receiver")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--ports",
        type=str,
        default=None,
        help="Comma-separated UDP ports (default: 5001,5002,5003)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Listen on one UDP port only (backward compatibility)"
    )
    parser.add_argument("--log", default="logs/received.csv")
    args = parser.parse_args()

    try:
        if args.port is not None:
            ports = [args.port]
        elif args.ports is not None:
            ports = [int(p.strip()) for p in args.ports.split(",")]
        else:
            ports = DEFAULT_PORTS

        if not ports or len(set(ports)) != len(ports):
            parser.error("Ports must be non-empty and unique")

        if any(not 1 <= port <= 65535 for port in ports):
            parser.error("All ports must be between 1 and 65535")

    except ValueError:
        parser.error("Invalid port list")

    folder = os.path.dirname(args.log)
    if folder:
        os.makedirs(folder, exist_ok=True)

    sessions = {}
    total_packets = 0
    total_bytes = 0

    sockets = []

    try:
        for port in ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((args.host, port))
            sockets.append(sock)

        print(f"Listening on {args.host} ports: {', '.join(map(str, ports))}")
        print("Press Ctrl+C to stop.")

        with open(args.log, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "receive_time_unix", "session_id", "traffic_class",
                "sequence", "sender_time_unix", "apparent_delay_ms",
                "interarrival_ms", "source_ip", "source_port",
                "payload_bytes"
            ])

            try:
                while True:
                    readable, _, _ = select.select(sockets, [], [], 1.0)

                    for sock in readable:
                        data, address = sock.recvfrom(65535)
                        receive_unix = time.time()
                        receive_mono = time.monotonic()
                        destination_port = sock.getsockname()[1]

                        try:
                            message = json.loads(data.decode("utf-8"))

                            if not isinstance(message, dict):
                                raise ValueError("Expected JSON object")

                            if message.get("version") != VERSION:
                                raise ValueError("Unsupported packet version")

                            kind = message["type"]
                            session_id = message["session_id"]
                            traffic_class = message["traffic_class"]

                            if traffic_class not in TRAFFIC_CLASSES:
                                raise ValueError("Unknown traffic class")

                            if not isinstance(session_id, str) or not session_id:
                                raise ValueError("Invalid session ID")

                            expected_port = {
                                "voice": 5001,
                                "video": 5002,
                                "best_effort": 5003
                            }[traffic_class]

                            if destination_port != expected_port:
                                raise ValueError(
                                    f"{traffic_class} should use UDP "
                                    f"port {expected_port}, received on "
                                    f"{destination_port}"
                                )

                            key = (session_id, traffic_class)

                            if kind == "END":
                                expected = int(message["total_sent"])

                                if expected < 0:
                                    raise ValueError("Invalid total_sent")

                                state = sessions.setdefault(key, new_session())
                                state["expected"] = expected

                                print(
                                    f"End marker: class={traffic_class}, "
                                    f"sender reported {expected} packets"
                                )
                                continue

                            if kind != "DATA":
                                raise ValueError("Unknown packet type")

                            sequence = int(message["sequence"])
                            sender_time = float(message["send_time_unix"])

                            if sequence < 0:
                                raise ValueError("Invalid sequence number")

                        except (
                            UnicodeDecodeError, json.JSONDecodeError,
                            KeyError, TypeError, ValueError, OverflowError
                        ) as exc:
                            print(
                                f"Ignoring malformed packet from {address}: {exc}"
                            )
                            continue

                        state = sessions.setdefault(key, new_session())
                        state["received"] += 1

                        if sequence in state["sequences"]:
                            state["duplicates"] += 1
                        else:
                            state["sequences"].add(sequence)

                        previous = state["last_mono"]
                        interarrival = (
                            (receive_mono - previous) * 1000
                            if previous is not None else None
                        )

                        if interarrival is not None:
                            state["intervals"].append(interarrival)

                        state["last_mono"] = receive_mono

                        delay = (receive_unix - sender_time) * 1000
                        state["delays"].append(delay)
                        state["bytes"] += len(data)

                        if state["first"] is None:
                            state["first"] = receive_mono

                        state["last"] = receive_mono

                        total_packets += 1
                        total_bytes += len(data)

                        writer.writerow([
                            receive_unix, session_id, traffic_class,
                            sequence, sender_time, round(delay, 3),
                            round(interarrival, 3)
                            if interarrival is not None else "",
                            address[0], address[1], len(data)
                        ])

                        if total_packets % 50 == 0:
                            file.flush()
                            print(f"Received {total_packets} DATA packets")

            except KeyboardInterrupt:
                print("\nStopping receiver...")

    except OSError as exc:
        print(f"Receiver error: {exc}")
        return

    finally:
        for sock in sockets:
            sock.close()

    packet_times = [
        (state["first"], state["last"])
        for state in sessions.values()
        if state["first"] is not None and state["last"] is not None
    ]

    if packet_times:
        first_packet = min(first for first, last in packet_times)
        last_packet = max(last for first, last in packet_times)
        elapsed = max(last_packet - first_packet, 0.001)
    else:
        elapsed = 0.001

    print("\n========== RECEIVER SUMMARY ==========")
    print(f"DATA packets received: {total_packets}")
    print(f"Payload received: {total_bytes} bytes")
    print(f"Overall receive rate: {total_packets / elapsed:.2f} packets/s")
    print(f"Overall payload throughput: {total_bytes * 8 / elapsed:.2f} bits/s")

    for (session_id, traffic_class), state in sessions.items():
        sequences = state["sequences"]
        expected = state["expected"]

        print(f"\nClass: {traffic_class} | Session: {session_id[:8]}")
        print(f"Packets received: {state['received']}")
        print(f"Unique sequence numbers: {len(sequences)}")
        print(f"Duplicate packets: {state['duplicates']}")

        if expected is not None:
            in_range = sum(1 for seq in sequences if 0 <= seq < expected)
            missing = max(expected - in_range, 0)
            loss = 100 * missing / expected if expected else 0.0

            print(f"Sender-reported packets: {expected}")
            print(f"Unique packets in expected range: {in_range}")
            print(f"Estimated missing packets: {missing}")
            print(f"Estimated packet loss: {loss:.2f}%")

        if state["delays"]:
            mean_delay = sum(state["delays"]) / len(state["delays"])
            print(f"Mean apparent one-way delay: {mean_delay:.3f} ms")

        intervals = state["intervals"]

        if len(intervals) >= 2:
            jitter = sum(
                abs(intervals[i] - intervals[i - 1])
                for i in range(1, len(intervals))
            ) / (len(intervals) - 1)

            print(f"Interarrival variation estimate: {jitter:.3f} ms")

        first, last = state["first"], state["last"]

        if first is not None and last is not None and last > first:
            throughput = state["bytes"] * 8 / (last - first)
            print(f"Class payload throughput: {throughput:.2f} bits/s")

    print(f"\nCSV log: {args.log}")
    print("One-way delay requires synchronized sender/receiver clocks.")


if __name__ == "__main__":
    main()
