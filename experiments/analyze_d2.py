import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOG_DIR = BASE / "logs" / "d2"
RESULT_DIR = BASE / "results" / "d2"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

senders = [
    "client1_voice.csv",
    "client2_video.csv",
    "client3_best_effort.csv"
]

sent_frames = [pd.read_csv(LOG_DIR / f) for f in senders]
sent = pd.concat(sent_frames, ignore_index=True)

received = pd.concat([
    pd.read_csv(LOG_DIR / "server1_received.csv"),
    pd.read_csv(LOG_DIR / "server2_received.csv")
], ignore_index=True)

rows = []

for traffic_class in ["voice", "video", "best_effort"]:
    sent_class = sent[sent["traffic_class"] == traffic_class]
    session_ids = sent_class["session_id"].unique()

    recv_class = received[
        (received["traffic_class"] == traffic_class) &
        (received["session_id"].isin(session_ids))
    ].copy()

    total_sent = len(sent_class[sent_class["status"] == "sent"])
    total_received = len(recv_class)

    loss = max(total_sent - total_received, 0)
    loss_percent = loss / total_sent * 100 if total_sent else 0

    avg_delay = recv_class["apparent_delay_ms"].mean()

    intervals = recv_class["interarrival_ms"].dropna()
    avg_jitter = (
        (intervals - intervals.mean()).abs().mean()
        if len(intervals) else 0
    )

    duration = (
        recv_class["receive_time_unix"].max()
        - recv_class["receive_time_unix"].min()
    )

    throughput = (
        recv_class["payload_bytes"].sum() * 8 / duration / 1000
        if duration > 0 else 0
    )

    rows.append({
        "Traffic Class": traffic_class,
        "Packets Sent": total_sent,
        "Packets Received": total_received,
        "Estimated Packet Loss (%)": round(loss_percent, 2),
        "Average Delay (ms)": round(avg_delay, 3),
        "Average Jitter (ms)": round(avg_jitter, 3),
        "Throughput (Kbps)": round(throughput, 2)
    })

metrics = pd.DataFrame(rows)
metrics.to_csv(RESULT_DIR / "d2_performance_metrics.csv", index=False)

print("\nD2 CONCURRENT TEST PERFORMANCE\n")
print(metrics.to_string(index=False))

for column, filename, ylabel in [
    ("Average Delay (ms)", "delay.png", "Delay (ms)"),
    ("Average Jitter (ms)", "jitter.png", "Jitter (ms)"),
    ("Throughput (Kbps)", "throughput.png", "Throughput (Kbps)"),
    ("Estimated Packet Loss (%)", "packet_loss.png", "Packet Loss (%)")
]:
    plt.figure()
    plt.bar(metrics["Traffic Class"], metrics[column])
    plt.xlabel("Traffic Class")
    plt.ylabel(ylabel)
    plt.title("D2 " + ylabel + " Comparison")
    plt.tight_layout()
    plt.savefig(RESULT_DIR / filename)
    plt.close()

print("\nCorrected metrics and graphs saved in results/d2/")
