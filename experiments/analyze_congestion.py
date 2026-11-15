import pandas as pd
from pathlib import Path

base = Path(__file__).resolve().parent.parent
log_dir = base / "logs" / "d2"
result_dir = base / "results" / "d2"

received = pd.read_csv(log_dir / "server1_received.csv")

tests = [
    ("Voice", "congestion_client1.csv"),
    ("Best Effort", "congestion_client3.csv")
]

results = []

for name, filename in tests:
    sent = pd.read_csv(log_dir / filename)
    session_ids = sent["session_id"].unique()

    sent_count = len(sent[sent["status"] == "sent"])

    recv = received[received["session_id"].isin(session_ids)]

    received_count = len(recv)
    loss = max(sent_count - received_count, 0)

    delay = recv["apparent_delay_ms"].mean()

    intervals = recv["interarrival_ms"].dropna()
    jitter = (
        (intervals - intervals.mean()).abs().mean()
        if len(intervals) else 0
    )

    duration = (
        recv["receive_time_unix"].max()
        - recv["receive_time_unix"].min()
    )

    throughput = (
        recv["payload_bytes"].sum() * 8 / duration / 1000
        if duration > 0 else 0
    )

    results.append({
        "Traffic Class": name,
        "Packets Sent": sent_count,
        "Packets Received": received_count,
        "Estimated Packet Loss (%)": round(loss / sent_count * 100, 2),
        "Average Delay (ms)": round(delay, 3),
        "Average Jitter (ms)": round(jitter, 3),
        "Throughput (Kbps)": round(throughput, 2)
    })

metrics = pd.DataFrame(results)
metrics.to_csv(result_dir / "congestion_performance_metrics.csv", index=False)

print("\nCONGESTION TEST PERFORMANCE\n")
print(metrics.to_string(index=False))
print("\nSaved to results/d2/congestion_performance_metrics.csv")

import matplotlib.pyplot as plt

for column, filename, ylabel in [
    ("Estimated Packet Loss (%)", "congestion_packet_loss.png", "Packet Loss (%)"),
    ("Average Delay (ms)", "congestion_delay.png", "Delay (ms)"),
    ("Average Jitter (ms)", "congestion_jitter.png", "Jitter (ms)"),
    ("Throughput (Kbps)", "congestion_throughput.png", "Throughput (Kbps)")
]:
    plt.figure()
    plt.bar(metrics["Traffic Class"], metrics[column])
    plt.ylabel(ylabel)
    plt.title("D2 Congestion Test - " + ylabel)
    plt.tight_layout()
    plt.savefig(result_dir / filename)
    plt.close()

print("Congestion graphs saved.")
