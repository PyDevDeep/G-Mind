from prometheus_client import Counter, Histogram

# Лічильник оброблених листів (з розбивкою за фінальним статусом)
EMAILS_PROCESSED = Counter(
    "emails_processed_total", "Total emails processed by AI", ["status"]
)

# Гістограма тривалості класифікації
CLASSIFICATION_LATENCY = Histogram(
    "classification_latency_seconds",
    "Latency of AI classification process",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0],
)
