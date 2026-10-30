import argparse
import csv
import json
import os
import socket
import time
import uuid

TRAFFIC_CLASSES = ("voice", "video", "best_effort")
VERSION = 1


def encode_packet(message, size=None):
    data = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if size is not None:
        if len(data) > size:
            raise ValueError("Payload size is too small for packet metadata")
        data += b" " * (size - len(data))
    return data


def main():
    parser = argparse.ArgumentParser(description="QoS UDP traffic sender")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--class-name", choices=TRAFFIC_CLASSES,
                        default="best_effort")
    parser.add_argument("--rate", type=float, default=20.0,
                        help="Target packets per second")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--payload-size", type=int, default=256)
    parser.add_argument("--log", default="logs/sent.csv")
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.rate <= 0 or args.duration <= 0:
        parser.error("--rate and --duration must be positive")
    if not 128 <= args.payload_size <= 60000:
        parser.error("--payload-size must be between 128 and 60000")

    folder = os.path.dirname(args.log)
    if folder:
        os.makedirs(folder, exist_ok=True)

    session = str(uuid.uuid4())
    interval = 1.0 / args.rate
    start = time.monotonic()
    deadline = start + args.duration
    sent = 0
    errors = 0

    print(f"Session: {session}")
    print(f"Sending {args.class_name} to {args.host}:{args.port}")
    print(f"Target: {args.rate} packets/s for {args.duration} seconds")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        with open(args.log, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "session_id", "traffic_class", "sequence",
                "send_time_unix", "payload_bytes", "status"
            ])

            try:
                while time.monotonic() < deadline:
                    now = time.time()
                    message = {
                        "version": VERSION,
                        "type": "DATA",
                        "session_id": session,
                        "traffic_class": args.class_name,
                        "sequence": sent,
                        "send_time_unix": now,
                    }

                    try:
                        packet = encode_packet(message, args.payload_size)
                        sock.sendto(packet, (args.host, args.port))
                        writer.writerow([
                            session, args.class_name, sent,
                            now, len(packet), "sent"
                        ])
                        sent += 1
                    except (OSError, ValueError) as exc:
                        errors += 1
                        print(f"Send error: {exc}")
                        if isinstance(exc, ValueError):
                            break

                    if sent % 100 == 0:
                        file.flush()

                    target = start + sent * interval
                    remaining = target - time.monotonic()
                    if remaining > 0:
                        time.sleep(remaining)

            except KeyboardInterrupt:
                print("\nInterrupted; finalizing sender session.")

            # Repeat the end marker to reduce the chance it is lost.
            end_message = {
                "version": VERSION,
                "type": "END",
                "session_id": session,
                "traffic_class": args.class_name,
                "total_sent": sent,
                "end_time_unix": time.time(),
            }
            try:
                marker = encode_packet(end_message)
                for _ in range(3):
                    sock.sendto(marker, (args.host, args.port))
                    time.sleep(0.02)
            except OSError as exc:
                print(f"Could not send end marker: {exc}")

    elapsed = max(time.monotonic() - start, 0.001)
    print("\n--- Sender summary ---")
    print(f"Packets sent: {sent}")
    print(f"Send errors: {errors}")
    print(f"Elapsed: {elapsed:.2f} seconds")
    print(f"Actual rate: {sent / elapsed:.2f} packets/s")
    print(f"CSV log: {args.log}")


if __name__ == "__main__":
    main()
