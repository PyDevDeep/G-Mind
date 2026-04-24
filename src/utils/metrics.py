from prometheus_client import Counter, Histogram

# Counter of processed emails broken down by final status
EMAILS_PROCESSED = Counter(
    "emails_processed_total", "Total emails processed by AI", ["status"]
)

# Histogram of AI classification duration
CLASSIFICATION_LATENCY = Histogram(
    "classification_latency_seconds",
    "Latency of AI classification process",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0],
)
