
import argparse
import csv
import json
import os
import select
import socket
import time
from collections import defaultdict


CLASS_PORTS = {
    "voice": 5001,
    "video": 5002,
    "best_effort": 5003,
}

CSV_FIELDS = [
    "receive_time_unix",
    "session_id",
    "traffic_class",
    "sequence",
    "sender_time_unix",
    "apparent_delay_ms",
    "interarrival_ms",
    "source_ip",
    "source_port",
    "payload_bytes",
]


def main():
    parser = argparse.ArgumentParser(
        description="QoS UDP traffic receiver"
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--ports",
        default="5001,5002,5003",
        help="Comma-separated UDP ports"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Listen on one UDP port only (backward compatibility)"
    )
    parser.add_argument("--log", default="logs/received.csv")
    args = parser.parse_args()

    ports = (
        [args.port]
        if args.port is not None
        else [int(p.strip()) for p in args.ports.split(",")]
    )

    sockets = []
    sessions = {}
    class_stats = defaultdict(
        lambda: {
            "received": 0,
            "sequences": set(),
            "delays": [],
            "interarrivals": [],
            "bytes": 0,
            "sender_reported": None,
        }
    )

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)

    csv_file = open(args.log, "w", newline="")
    writer = csv.DictWriter(
        csv_file,
        fieldnames=CSV_FIELDS
    )
    writer.writeheader()

    total_packets = 0
    total_bytes = 0
    first_receive_time = None
    last_receive_time = None

    try:
        for port in ports:
            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM
            )
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1
            )
            sock.bind((args.host, port))
            sockets.append(sock)

        print(
            f"Listening on {args.host} ports: "
            + ", ".join(map(str, ports))
        )
        print("Press Ctrl+C to stop.")

        while True:
            readable, _, _ = select.select(
                sockets, [], [], 1.0
            )

            for sock in readable:
                data, address = sock.recvfrom(65535)
                receive_time = time.time()
                receive_port = sock.getsockname()[1]

                try:
                    packet = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

                packet_type = packet.get("type")
                session_id = packet.get("session_id")

                if packet_type == "END":
                    if session_id in sessions:
                        sessions[session_id]["sender_reported"] = (
                            packet.get("total_sent")
                        )
                    continue

                if packet_type != "DATA":
                    continue

                traffic_class = packet.get("traffic_class")
                sequence = packet.get("sequence")
                sender_time = packet.get("send_time_unix")

                if traffic_class not in CLASS_PORTS:
                    print(
                        f"Unknown traffic class: {traffic_class}"
                    )
                    continue

                if CLASS_PORTS[traffic_class] != receive_port:
                    print(
                        f"Port mismatch: {traffic_class} "
                        f"received on {receive_port}"
                    )
                    continue

                if session_id is None or sequence is None:
                    continue

                try:
                    sequence = int(sequence)
                    sender_time = float(sender_time)
                except (TypeError, ValueError):
                    continue

                payload_bytes = len(data)
                apparent_delay_ms = (
                    receive_time - sender_time
                ) * 1000

                session = sessions.setdefault(
                    session_id,
                    {
                        "traffic_class": traffic_class,
                        "last_receive_time": None,
                        "sender_reported": None,
                    },
                )

                previous_time = session["last_receive_time"]
                interarrival_ms = (
                    (receive_time - previous_time) * 1000
                    if previous_time is not None
                    else None
                )
                session["last_receive_time"] = receive_time

                stats = class_stats[
                    (traffic_class, session_id)
                ]
                stats["received"] += 1
                stats["sequences"].add(sequence)
                stats["delays"].append(apparent_delay_ms)
                stats["bytes"] += payload_bytes

                if interarrival_ms is not None:
                    stats["interarrivals"].append(
                        interarrival_ms
                    )

                total_packets += 1
                total_bytes += payload_bytes

                if first_receive_time is None:
                    first_receive_time = receive_time
                last_receive_time = receive_time

                writer.writerow({
                    "receive_time_unix": receive_time,
                    "session_id": session_id,
                    "traffic_class": traffic_class,
                    "sequence": sequence,
                    "sender_time_unix": sender_time,
                    "apparent_delay_ms": apparent_delay_ms,
                    "interarrival_ms": interarrival_ms,
                    "source_ip": address[0],
                    "source_port": address[1],
                    "payload_bytes": payload_bytes,
                })
                csv_file.flush()

    except KeyboardInterrupt:
        print("\nStopping receiver...")

    finally:
        for sock in sockets:
            sock.close()
        csv_file.close()

    print("\n========== RECEIVER SUMMARY ==========")
    print(f"DATA packets received: {total_packets}")
    print(f"Payload received: {total_bytes} bytes")

    if first_receive_time is not None:
        elapsed = last_receive_time - first_receive_time
        if elapsed > 0:
            print(
                f"Overall receive rate: "
                f"{total_packets / elapsed:.2f} packets/s"
            )
            print(
                f"Overall payload throughput: "
                f"{total_bytes * 8 / elapsed:.2f} bits/s"
            )

    for (traffic_class, session_id), stats in class_stats.items():
        received = stats["received"]
        unique = len(stats["sequences"])
        reported = sessions[session_id]["sender_reported"]

        missing = (
            max(0, int(reported) - unique)
            if reported is not None
            else None
        )
        loss = (
            missing / int(reported) * 100
            if reported and int(reported) > 0
            else None
        )

        mean_delay = (
            sum(stats["delays"]) / len(stats["delays"])
            if stats["delays"]
            else 0
        )

        jitter = (
            sum(stats["interarrivals"]) /
            len(stats["interarrivals"])
            if stats["interarrivals"]
            else 0
        )

        print(
            f"\nClass: {traffic_class} | "
            f"Session: {session_id[:8]}"
        )
        print(f"Packets received: {received}")
        print(f"Unique sequence numbers: {unique}")
        print(f"Duplicate packets: {received - unique}")
        print(f"Sender-reported packets: {reported}")
        print(f"Estimated missing packets: {missing}")
        print(
            f"Estimated packet loss: "
            f"{loss:.2f}%"
            if loss is not None
            else "Estimated packet loss: unavailable"
        )
        print(
            f"Mean apparent one-way delay: "
            f"{mean_delay:.3f} ms"
        )
        print(
            f"Interarrival variation estimate: "
            f"{jitter:.3f} ms"
        )

    print(f"\nCSV log: {args.log}")
    print(
        "One-way delay requires synchronized sender/receiver clocks."
    )


if __name__ == "__main__":
    main()
