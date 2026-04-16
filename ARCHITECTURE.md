# Architecture Documentation 🏛️

This document describes the architecture, design decisions, and technical implementation details of AI Email Assistant.

## Table of Contents

- [System Overview](#system-overview)
- [Component Architecture](#component-architecture)
- [Data Flow](#data-flow)
- [Technology Decisions](#technology-decisions)
- [Database Schema](#database-schema)
- [API Design](#api-design)
- [Worker Architecture](#worker-architecture)
- [Monitoring & Observability](#monitoring--observability)
- [Security Architecture](#security-architecture)
- [Scalability Considerations](#scalability-considerations)
- [Architecture Decision Records](#architecture-decision-records)

## System Overview

AI Email Assistant is a distributed system designed to process Gmail emails asynchronously using Large Language Models. The system follows a event-driven architecture with clear separation between the HTTP layer, task orchestration, and business logic.

### Core Principles

1. **Asynchronous Processing**: Webhooks return immediately; all processing happens asynchronously
2. **Fault Tolerance**: Retry logic at every integration point with exponential backoff
3. **Observability First**: All operations emit structured logs and metrics
4. **Stateless Workers**: Celery workers can scale horizontally without coordination
5. **Data Integrity**: Database transactions ensure consistency across operations

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              External Services                               │
├──────────────┬────────────────────┬────────────────┬────────────────────────┤
│  Gmail API   │  Google Pub/Sub    │  OpenAI API    │  Anthropic Claude API  │
└──────┬───────┴──────────┬─────────┴────────┬───────┴────────────┬───────────┘
       │                  │                  │                    │
       │                  ▼                  │                    │
       │          ┌───────────────┐          │                    │
       │          │   FastAPI     │          │                    │
       │          │   Webhook     │          │                    │
       │          │   Handler     │          │                    │
       │          └───────┬───────┘          │                    │
       │                  │                  │                    │
       │                  ▼                  │                    │
       │          ┌───────────────┐          │                    │
       │          │  PostgreSQL   │          │                    │
       │          │  Task Queue   │◄─────────┼────────────────────┤
       │          └───────┬───────┘          │                    │
       │                  │                  │                    │
       │                  ▼                  │                    │
       │          ┌───────────────┐          │                    │
       │          │     Redis     │          │                    │
       │          │  Celery Broker│          │                    │
       │          └───────┬───────┘          │                    │
       │                  │                  │                    │
       └──────────────────┼──────────────────┼────────────────────┘
                          │                  │
              ┌───────────┴─────────┬────────┴────────┬──────────┐
              ▼                     ▼                 ▼          ▼
      ┌────────────┐        ┌────────────┐   ┌────────────┐  ┌────────┐
      │  Worker 1  │        │  Worker 2  │   │  Worker N  │  │ Beat   │
      │ (classify) │        │ (generate) │   │   (send)   │  │Scheduler│
      └────────────┘        └────────────┘   └────────────┘  └────────┘
              │                     │                 │
              └─────────────────────┴─────────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   Monitoring Stack     │
              │ Prometheus + Grafana   │
              │   Loki + Alertmanager  │
              └────────────────────────┘
```

## Component Architecture

### 1. FastAPI Application Layer

**Responsibilities:**
- Receive and validate Pub/Sub webhook notifications
- Provide health check and metrics endpoints
- Enforce rate limiting
- Manage database sessions via dependency injection

**Key Files:**
- `src/main.py` - Application factory and lifespan management
- `src/api/webhook.py` - Pub/Sub webhook handler
- `src/api/router.py` - Route registration
- `src/dependencies.py` - Dependency injection setup

**Technology:**
- FastAPI with async/await
- Uvicorn ASGI server
- Pydantic for request/response validation

**Design Patterns:**
- Dependency Injection for database sessions
- Repository pattern for data access
- Service layer for business logic

### 2. Database Layer

**Technology:** PostgreSQL 15+ with SQLAlchemy 2.0 async ORM

**Design Decisions:**
- Async drivers (`asyncpg`) for non-blocking I/O
- Connection pooling (20 connections, 10 overflow)
- Alembic for schema migrations with auto-generation
- UTC timestamps across all tables
- Indexed foreign keys for query performance

**Tables:**

```sql
-- Email metadata
emails (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(255) UNIQUE NOT NULL,  -- Gmail message ID
    thread_id VARCHAR(255),
    sender VARCHAR(255),
    subject TEXT,
    received_at TIMESTAMP WITH TIME ZONE,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)

-- Processing tasks
processing_tasks (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    status VARCHAR(50),  -- pending, processing, completed, failed
    stage VARCHAR(50),   -- classify, generate, send
    correlation_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
)

-- AI-generated responses
ai_responses (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    category VARCHAR(50),  -- needs_reply, informational, spam
    confidence FLOAT,
    generated_reply TEXT,
    model_used VARCHAR(100),
    tokens_used INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)

-- Dead-letter queue for failed tasks
failed_tasks (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    task_name VARCHAR(255),
    error_message TEXT,
    stack_trace TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
)
```

**Indexes:**
```sql
CREATE INDEX idx_emails_message_id ON emails(message_id);
CREATE INDEX idx_emails_processed ON emails(processed);
CREATE INDEX idx_tasks_status ON processing_tasks(status);
CREATE INDEX idx_tasks_correlation_id ON processing_tasks(correlation_id);
CREATE INDEX idx_failed_tasks_resolved ON failed_tasks(resolved_at);
```

### 3. Celery Worker Layer

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                     Celery Beat (Scheduler)                  │
│  - Gmail watch renewal (every 6 days)                        │
│  - Failed task retry (hourly)                                │
│  - Metrics aggregation (every 5 minutes)                     │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Redis (Message Broker)                   │
│  Queues:                                                     │
│  - default: General purpose tasks                            │
│  - priority: High priority tasks                             │
│  - dead_letter: Failed tasks after max retries               │
└─────────────────────────────────────────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
    ┌───────────┐     ┌───────────┐     ┌───────────┐
    │  Worker   │     │  Worker   │     │  Worker   │
    │    #1     │     │    #2     │     │    #N     │
    └───────────┘     └───────────┘     └───────────┘
```

**Task Pipeline:**

```
classify_email(email_id)
    │
    ├─ Fetch email from Gmail API
    ├─ Extract text content (sanitize HTML)
    ├─ Call LLM for classification
    ├─ Store result in database
    │
    └─ IF category == "needs_reply":
           │
           └─> generate_ai_reply(email_id)
                   │
                   ├─ Fetch email context
                   ├─ Call LLM for response generation
                   ├─ Store generated reply
                   │
                   └─> send_draft(email_id)
                           │
                           ├─ Format draft message
                           ├─ Create Gmail draft via API
                           └─ Update task status
```

**Retry Strategy:**

```python
Task Type         | Max Retries | Backoff | Backoff Max | Retriable Errors
------------------|-------------|---------|-------------|------------------
classify_email    | 5           | 60s     | 900s        | LLMRateLimitError, GmailAPIError
generate_ai_reply | 3           | 60s     | 600s        | LLMRateLimitError, GmailAPIError
send_draft        | 3           | 30s     | 300s        | GmailAPIError
```

**Concurrency Configuration:**

```python
# Production settings
CELERY_WORKER_CONCURRENCY = 4  # Tasks per worker process
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Tasks to prefetch
CELERY_TASK_ACKS_LATE = True  # Ack after completion
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # Requeue on crash
```

### 4. External API Integration

#### Gmail API

**Endpoints Used:**
- `users.messages.get()` - Fetch email content (5 quota units)
- `users.drafts.create()` - Create draft (10 quota units)
- `users.watch()` - Set up push notifications (2 quota units)

**Quota Management:**
- User quota: 250 units/second, 1 billion/day
- Exponential backoff: `min(60 * 2^n, 900)` seconds
- Redis-based rate limiter to prevent quota exhaustion

**Authentication Flow:**

```
1. OAuth 2.0 Authorization Code Flow (one-time setup)
   User → Browser → Google OAuth → Authorization Code → Token Exchange

2. Token Storage
   {
     "token": "ya29.a0...",           # Short-lived access token (1 hour)
     "refresh_token": "1//0...",      # Long-lived refresh token
     "token_uri": "https://oauth2.googleapis.com/token",
     "client_id": "...",
     "client_secret": "...",
     "scopes": ["https://www.googleapis.com/auth/gmail.modify"]
   }

3. Token Refresh (automatic)
   Worker detects expired token → Use refresh token → Get new access token
```

#### LLM API Integration

**Primary: OpenAI GPT-4**

```python
Classification Prompt:
"""
Analyze the following email and categorize it into one of these categories:
1. needs_reply - Email requires a response from the user
2. informational - Email is FYI only, no response needed
3. spam - Unsolicited or irrelevant content

Email Details:
From: {sender}
Subject: {subject}
Content: {body}

Respond with JSON:
{
  "category": "needs_reply|informational|spam",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}
"""

Response Generation Prompt:
"""
Generate a professional email response to the following message.
Consider the sender's tone, urgency, and any questions asked.

Original Email:
From: {sender}
Subject: {subject}
Content: {body}

Generate a response that:
- Addresses all points raised
- Maintains professional tone
- Is concise (under 200 words)

Respond with plain text only (no JSON).
"""
```

**Fallback: Anthropic Claude**

Activated when:
- OpenAI API returns 5xx errors
- Rate limit hit and retry exhausted
- Circuit breaker opens (3 consecutive failures)

**Model Configuration:**

```python
OPENAI_CONFIG = {
    "model": "gpt-4-turbo-preview",
    "temperature": 0.3,  # Lower for consistency
    "max_tokens": 500,
    "top_p": 1.0
}

CLAUDE_CONFIG = {
    "model": "claude-3-sonnet-20240229",
    "max_tokens": 1000,
    "temperature": 0.3
}
```

## Data Flow

### 1. Email Reception Flow

```
Gmail Inbox
    │
    │ (New email arrives)
    ▼
Gmail Push Notification
    │
    │ (Pub/Sub publishes message)
    ▼
FastAPI Webhook Endpoint
    │
    ├─ Verify Pub/Sub token
    ├─ Decode base64 payload
    ├─ Extract email_id and history_id
    │
    ├─ Check deduplication (query emails table)
    │
    ├─ Create Email record
    ├─ Create ProcessingTask record
    │
    ├─ Dispatch classify_email.delay(email_id)
    │
    └─ Return 204 (acknowledge to Pub/Sub)
        │
        └─ (Pub/Sub marks message as delivered)
```

### 2. Classification Flow

```
classify_email task receives email_id
    │
    ├─ Bind correlation_id to logger
    ├─ Update task status → "processing"
    │
    ├─ Fetch email content from Gmail API
    │   ├─ Rate limit check
    │   ├─ API call with retry
    │   └─ Extract headers + body
    │
    ├─ Sanitize HTML content
    │   └─ BeautifulSoup.get_text()
    │
    ├─ Call LLM API
    │   ├─ Format prompt
    │   ├─ Send request (with timeout)
    │   ├─ Parse JSON response
    │   └─ Validate schema
    │
    ├─ Store AIResponse record
    │   ├─ category
    │   ├─ confidence
    │   ├─ model_used
    │   └─ tokens_used
    │
    ├─ Update task stage → "classified"
    │
    └─ IF category == "needs_reply":
           └─ Dispatch generate_ai_reply.delay(email_id)
```

### 3. Reply Generation Flow

```
generate_ai_reply task receives email_id
    │
    ├─ Fetch email and previous AIResponse
    │
    ├─ Build context for LLM
    │   ├─ Original email content
    │   ├─ Sender information
    │   └─ Classification result
    │
    ├─ Call LLM API
    │   ├─ Format response generation prompt
    │   ├─ Send request
    │   └─ Extract generated text
    │
    ├─ Update AIResponse.generated_reply
    │
    ├─ Update task stage → "reply_generated"
    │
    └─ Dispatch send_draft.delay(email_id)
```

### 4. Draft Creation Flow

```
send_draft task receives email_id
    │
    ├─ Fetch email and AIResponse
    │
    ├─ Format Gmail draft
    │   ├─ To: original sender
    │   ├─ Subject: Re: {original_subject}
    │   ├─ Body: generated_reply
    │   ├─ In-Reply-To: original message_id
    │   └─ References: original message_id
    │
    ├─ Create draft via Gmail API
    │   ├─ Rate limit check
    │   ├─ API call
    │   └─ Get draft_id
    │
    ├─ Update AIResponse.draft_id
    │
    ├─ Update task status → "completed"
    ├─ Update email.processed → TRUE
    │
    └─ Emit metrics
        ├─ pipeline_duration_seconds
        └─ pipeline_success_total
```

## Technology Decisions

### Why FastAPI?

**Chosen over:** Flask, Django, Starlette

**Rationale:**
- Native async/await support (critical for I/O-bound workloads)
- Automatic OpenAPI documentation
- Pydantic integration for validation
- Type hints enable better IDE support and mypy checking
- High performance (comparable to Node.js/Go)

### Why Celery?

**Chosen over:** RQ, Dramatiq, Apache Airflow

**Rationale:**
- Battle-tested in production environments
- Rich retry/error handling mechanisms
- Supports multiple brokers (Redis, RabbitMQ)
- Canvas primitives for complex workflows
- Extensive monitoring/management tools (Flower)

**Trade-offs:**
- Heavier than RQ (acceptable for our scale)
- Python-only (not a concern)
- Requires broker (Redis already needed for caching)

### Why PostgreSQL over MongoDB?

**Rationale:**
- Email processing requires ACID transactions
- Relational data (emails → tasks → responses)
- Strong consistency guarantees
- Rich query capabilities with indexes
- Better support for complex aggregations

### Why Redis for Broker?

**Chosen over:** RabbitMQ, AWS SQS

**Rationale:**
- Simpler operational overhead
- Dual purpose: broker + result backend + rate limiter
- AOF persistence provides durability
- Fast in-memory operations
- Redis Cluster available for scaling

**Trade-offs:**
- Less reliable than RabbitMQ for message durability
- Requires persistence configuration (AOF/RDB)
- Mitigated by: idempotent tasks + deduplication

### Why Structured Logging (structlog)?

**Rationale:**
- Machine-parsable JSON output
- Correlation IDs for distributed tracing
- Metadata context preserved across async boundaries
- Integrates seamlessly with Loki/Elasticsearch
- Better than plain text for querying/alerting

## Database Schema

### Entity Relationship Diagram

```
┌──────────────────┐
│     emails       │
│──────────────────│
│ id (PK)          │
│ message_id       │◄─────────┐
│ thread_id        │          │
│ sender           │          │
│ subject          │          │
│ received_at      │          │
│ processed        │          │
│ created_at       │          │
└──────────────────┘          │
         │                    │
         │ 1:N                │ N:1
         ▼                    │
┌──────────────────┐          │
│ processing_tasks │          │
│──────────────────│          │
│ id (PK)          │          │
│ email_id (FK)    │──────────┘
│ status           │
│ stage            │
│ correlation_id   │
│ created_at       │
│ completed_at     │
└──────────────────┘
         │
         │ 1:1
         ▼
┌──────────────────┐
│  ai_responses    │
│──────────────────│
│ id (PK)          │
│ email_id (FK)    │──────────┐
│ category         │          │
│ confidence       │          │
│ generated_reply  │          │
│ model_used       │          │
│ tokens_used      │          │
│ draft_id         │          │
│ created_at       │          │
└──────────────────┘          │
                              │
                              │ N:1
                              │
┌──────────────────┐          │
│  failed_tasks    │          │
│──────────────────│          │
│ id (PK)          │          │
│ email_id (FK)    │──────────┘
│ task_name        │
│ error_message    │
│ stack_trace      │
│ retry_count      │
│ created_at       │
│ resolved_at      │
└──────────────────┘
```

### Migration Strategy

**Alembic Configuration:**

```python
# alembic/env.py
from src.models.base import Base

target_metadata = Base.metadata

# Async engine for migrations
config = context.config
engine = create_async_engine(config.get_main_option("sqlalchemy.url"))

async def run_migrations():
    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)
```

**Migration Naming:**
- Format: `YYYYMMDD_HHMMSS_description.py`
- Example: `20240416_143022_add_draft_id_to_responses.py`

**Safe Migration Practices:**
1. Always test migrations on copy of production data
2. Use `--autogenerate` but review changes manually
3. Add indexes concurrently in PostgreSQL
4. Never drop columns without backup
5. Use `op.batch_alter_table()` for SQLite compatibility

## API Design

### REST Principles

- Resource-oriented URLs
- HTTP methods indicate operations (GET, POST, PUT, DELETE)
- Status codes convey semantics (200, 201, 400, 404, 500)
- Versioning via URL prefix: `/api/v1/`

### Endpoint Design

```python
# Webhook endpoint
POST /api/webhook/gmail
Content-Type: application/json
Body: {
  "message": {
    "data": "base64_payload",
    "messageId": "123456",
    "publishTime": "2024-04-16T10:30:00Z"
  },
  "subscription": "projects/PROJECT/subscriptions/SUB"
}
Response: 204 No Content

# Manual processing trigger
POST /api/process-email
Content-Type: application/json
Body: {
  "email_id": "18f3a2b1c5d4e6f7",
  "force_reprocess": false
}
Response: 201 Created
{
  "task_id": "abc-123",
  "email_id": "18f3a2b1c5d4e6f7",
  "status": "pending",
  "created_at": "2024-04-16T10:30:00Z"
}

# Task status query
GET /api/task-status/{task_id}
Response: 200 OK
{
  "task_id": "abc-123",
  "email_id": "18f3a2b1c5d4e6f7",
  "status": "completed",
  "stage": "draft_created",
  "correlation_id": "uuid-here",
  "created_at": "2024-04-16T10:30:00Z",
  "completed_at": "2024-04-16T10:30:15Z",
  "ai_response": {
    "category": "needs_reply",
    "confidence": 0.95,
    "generated_reply": "...",
    "draft_id": "r-123456789"
  }
}

# Health check
GET /api/health
Response: 200 OK
{
  "status": "healthy",
  "timestamp": "2024-04-16T10:30:00Z",
  "services": {
    "database": "connected",
    "redis": "connected",
    "celery_workers": 3
  }
}

# Metrics (Prometheus format)
GET /api/metrics
Response: 200 OK (text/plain)
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",endpoint="/webhook"} 12345
```

### Error Response Format

```json
{
  "error": {
    "code": "INVALID_EMAIL_ID",
    "message": "Email ID must be alphanumeric",
    "details": {
      "field": "email_id",
      "provided": "invalid@value"
    },
    "timestamp": "2024-04-16T10:30:00Z",
    "request_id": "req-abc-123"
  }
}
```

## Worker Architecture

### Scaling Strategy

**Horizontal Scaling:**

```yaml
# docker-compose.yml
services:
  celery-worker:
    image: ai-email-assistant:latest
    command: celery -A src.workers.celery_app worker --loglevel=info
    deploy:
      replicas: 3  # Scale to 3 workers
```

**Autoscaling (Kubernetes):**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: celery-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: celery-worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: External
    external:
      metric:
        name: celery_queue_length
      target:
        type: AverageValue
        averageValue: "50"  # Scale up if queue > 50
```

### Task Routing

```python
# Route high-priority tasks to dedicated queue
CELERY_TASK_ROUTES = {
    'src.workers.tasks.classify_email': {'queue': 'default'},
    'src.workers.tasks.generate_ai_reply': {'queue': 'default'},
    'src.workers.tasks.send_draft': {'queue': 'priority'},
    'src.workers.tasks.bulk_reprocess': {'queue': 'batch'}
}
```

### Dead Letter Queue

Failed tasks (after exhausting retries) are caught by signal handler:

```python
@task_failure.connect
def handle_task_failure(sender, task_id, exception, args, kwargs, **other):
    """Log failed task to database for manual review."""
    email_id = args[0] if args else kwargs.get('email_id')
    
    async def store_failure():
        failed_task = FailedTask(
            email_id=email_id,
            task_name=sender.name,
            error_message=str(exception),
            stack_trace=traceback.format_exc(),
            retry_count=sender.max_retries
        )
        await db.add(failed_task)
        await db.commit()
    
    asyncio.run(store_failure())
```

## Monitoring & Observability

### Metrics Collection

**Custom Prometheus Metrics:**

```python
from prometheus_client import Counter, Histogram, Gauge

# HTTP metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# Task metrics
task_duration_seconds = Histogram(
    'celery_task_duration_seconds',
    'Task execution time',
    ['task_name', 'status'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120]
)

task_retry_total = Counter(
    'celery_task_retry_total',
    'Task retry count',
    ['task_name', 'reason']
)

# External API metrics
gmail_api_calls_total = Counter(
    'gmail_api_calls_total',
    'Gmail API calls',
    ['endpoint', 'status']
)

llm_api_latency_seconds = Histogram(
    'llm_api_latency_seconds',
    'LLM API response time',
    ['provider', 'model']
)

# Queue metrics
celery_queue_length = Gauge(
    'celery_queue_length',
    'Number of tasks in queue',
    ['queue']
)

# Business metrics
emails_processed_total = Counter(
    'emails_processed_total',
    'Total emails processed',
    ['category']
)
```

### Grafana Dashboards

**Dashboard 1: System Health**

Panels:
- API request rate (requests/sec)
- API latency (p50, p95, p99)
- Error rate (errors/sec)
- Active Celery workers
- Queue depth by queue name
- Database connection pool usage

**Dashboard 2: Email Pipeline**

Panels:
- Emails received (last hour)
- Classification distribution (pie chart)
- Pipeline success rate
- Average processing time
- LLM token usage
- Gmail API quota utilization

**Dashboard 3: External Dependencies**

Panels:
- Gmail API call rate
- Gmail API error rate
- OpenAI API latency
- Claude API fallback rate
- PostgreSQL query time
- Redis memory usage

### Alerting Rules

```yaml
# monitoring/alertmanager/alertmanager.yml
groups:
- name: email_assistant_alerts
  interval: 30s
  rules:
  
  # High queue depth
  - alert: HighQueueDepth
    expr: celery_queue_length{queue="default"} > 100
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Celery queue depth above threshold"
      description: "Queue {{ $labels.queue }} has {{ $value }} tasks pending"
  
  # Worker unavailable
  - alert: NoWorkersAvailable
    expr: sum(up{job="celery-worker"}) == 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "No Celery workers available"
  
  # Gmail quota approaching limit
  - alert: GmailQuotaNearLimit
    expr: gmail_api_quota_used / gmail_api_quota_limit > 0.8
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Gmail API quota at {{ $value | humanizePercentage }}"
  
  # High error rate
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
    for: 3m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"
      description: "{{ $value | humanize }} requests/sec failing"
```

## Security Architecture

### Authentication & Authorization

**Gmail OAuth Flow:**

```
1. Initial Setup (one-time, manual)
   Developer → OAuth Consent Screen → Google Authorization → tokens

2. Runtime Token Management
   Worker needs access → Check token expiry → If expired: refresh → Use fresh token
```

**Pub/Sub Webhook Security:**

```python
def verify_pubsub_token(token: str) -> bool:
    """Verify Google OIDC token from Pub/Sub."""
    try:
        # In production: use google-auth library
        id_info = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            audience=EXPECTED_AUDIENCE
        )
        
        # Verify issuer
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Invalid token issuer')
        
        return True
    except ValueError:
        logger.warning("Invalid Pub/Sub token")
        return False
```

### Secrets Management

**Development:** `.env` file (never committed)

**Production:** Environment variables configured on hosting platform

```python
# src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    DATABASE_URL: str
    REDIS_URL: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @validator('OPENAI_API_KEY')
    def validate_openai_key(cls, v):
        if not v.startswith('sk-'):
            raise ValueError('Invalid OpenAI API key format')
        return v
```

**Security Best Practices:**
- Never commit `.env` or `token.json` to git
- Use read-only file permissions: `chmod 600 .env token.json`
- Rotate API keys regularly (quarterly)
- Use separate keys for development/staging/production

### Input Validation

**Webhook Payload:**

```python
class PubSubMessage(BaseModel):
    data: str  # Base64 encoded
    messageId: str
    publishTime: datetime
    
    @validator('data')
    def decode_data(cls, v):
        try:
            decoded = base64.b64decode(v)
            return decoded.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Invalid base64 data: {e}")

class GmailNotification(BaseModel):
    emailAddress: EmailStr
    historyId: int
```

**HTML Sanitization:**

```python
def extract_clean_text(html_content: str) -> str:
    """Remove all HTML tags and scripts."""
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove dangerous elements
    for element in soup(["script", "style", "meta", "noscript"]):
        element.decompose()
    
    # Get clean text
    return soup.get_text(separator=" ", strip=True)
```

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/webhook/gmail")
@limiter.limit("100/minute")  # Max 100 webhooks per minute per IP
async def gmail_webhook(request: Request):
    pass
```

## Scalability Considerations

### Current Capacity

**Estimated Throughput:**
- Webhook endpoint: ~500 requests/sec (FastAPI + Uvicorn)
- Database writes: ~1000 inserts/sec (PostgreSQL)
- Celery workers: ~10 emails/sec per worker (limited by LLM API)

**Bottlenecks:**
1. **LLM API Rate Limits** (primary bottleneck)
   - OpenAI GPT-4: 3500 RPM → ~58 requests/sec
   - Worker concurrency must stay below this limit

2. **Gmail API Quota**
   - 250 units/sec per user
   - messages.get (5 units) → ~50 requests/sec

### Scaling Strategies

**Vertical Scaling (short-term):**
- Increase worker concurrency (4 → 8 tasks per worker)
- Upgrade LLM API tier (higher rate limits)
- Increase database connection pool

**Horizontal Scaling (long-term):**
- Deploy multiple worker pods in Kubernetes
- Use Redis Cluster for broker
- Implement read replicas for PostgreSQL
- Add pgbouncer for connection pooling

**Optimization Strategies:**
1. **Cache LLM responses** for similar emails (Redis)
2. **Batch processing** for non-urgent emails
3. **Priority queues** for VIP senders
4. **Email pre-filtering** to reduce LLM calls

### Multi-Tenant Architecture (Future)

For supporting multiple users:

```python
# Add user_id to all tables
emails (
    id,
    user_id,  # NEW: foreign key to users table
    message_id,
    ...
)

# Separate Redis keys per user
celery_queue:user_{user_id}:default

# Per-user rate limiting
@limiter.limit("50/minute", key_func=lambda: get_current_user().id)
```

## Architecture Decision Records

### ADR-001: Use PostgreSQL for Primary Database

**Status:** Accepted

**Context:**
Need a database for storing emails, tasks, and AI responses. Considered PostgreSQL, MongoDB, and DynamoDB.

**Decision:**
Use PostgreSQL with async SQLAlchemy.

**Consequences:**
- **Positive:** Strong ACID guarantees, rich query capabilities, mature ecosystem
- **Negative:** More complex scaling than NoSQL options
- **Mitigation:** Use read replicas and connection pooling for scale

---

### ADR-002: Celery for Async Task Processing

**Status:** Accepted

**Context:**
Email processing must be asynchronous to avoid blocking webhook responses. Evaluated Celery, RQ, and Dramatiq.

**Decision:**
Use Celery with Redis broker.

**Consequences:**
- **Positive:** Battle-tested, rich retry logic, extensive monitoring tools
- **Negative:** Heavier than alternatives, Python-only
- **Mitigation:** Redis already needed; overhead acceptable for reliability

---

### ADR-003: Structured Logging with structlog

**Status:** Accepted

**Context:**
Need machine-parsable logs for distributed tracing across async tasks.

**Decision:**
Use structlog with JSON output format.

**Consequences:**
- **Positive:** Easy to query in Loki/Elasticsearch, correlation IDs work seamlessly
- **Negative:** Slightly more verbose than plain logging
- **Mitigation:** Performance impact negligible

---

### ADR-004: Dual LLM Provider Strategy

**Status:** Accepted

**Context:**
OpenAI API outages would halt entire pipeline. Need fallback mechanism.

**Decision:**
Implement circuit breaker with Claude as fallback.

**Consequences:**
- **Positive:** Increased reliability, reduced downtime
- **Negative:** Additional API costs, prompt tuning for both providers
- **Mitigation:** Claude only activated on failures (< 5% of traffic)

---

### ADR-005: Gmail Watch Instead of IMAP Polling

**Status:** Accepted

**Context:**
Need near-real-time email processing. IMAP polling wastes resources and has latency.

**Decision:**
Use Gmail's watch() API with Pub/Sub webhooks.

**Consequences:**
- **Positive:** Real-time delivery, no polling overhead, scales automatically
- **Negative:** Requires public HTTPS endpoint, watch expires every 7 days
- **Mitigation:** Implement renewal cron job, use Cloud Run for webhook hosting

---

### ADR-006: FastAPI Over Flask

**Status:** Accepted

**Context:**
Need async-capable web framework for webhook endpoint.

**Decision:**
Use FastAPI instead of Flask.

**Consequences:**
- **Positive:** Native async/await, automatic OpenAPI docs, type validation
- **Negative:** Less mature ecosystem than Flask
- **Mitigation:** FastAPI is production-ready and well-maintained

---

## Diagram: Complete System Flow

```
                                 ┌────────────────────────┐
                                 │   Gmail Inbox          │
                                 │  (User's email account)│
                                 └───────────┬────────────┘
                                             │
                                             │ New email arrives
                                             ▼
                                 ┌────────────────────────┐
                                 │  Google Pub/Sub        │
                                 │  (Push notification)   │
                                 └───────────┬────────────┘
                                             │
                                             │ POST webhook
                                             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Application                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Webhook Handler                                                     │   │
│  │  1. Verify Pub/Sub token                                            │   │
│  │  2. Decode payload                                                   │   │
│  │  3. Check deduplication (email.message_id)                          │   │
│  │  4. Create Email + ProcessingTask records                           │   │
│  │  5. Dispatch classify_email.delay()                                 │   │
│  │  6. Return 204 (acknowledge)                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
                                 │ Task dispatched to Redis
                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                            Redis (Message Broker)                           │
│  Queues: [default], [priority], [dead_letter]                              │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
                                 │ Worker picks up task
                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         Celery Worker Pool                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  classify_email(email_id)                                            │   │
│  │  ├─ Fetch email via Gmail API                                       │   │
│  │  ├─ Sanitize HTML content                                           │   │
│  │  ├─ Call OpenAI API (or Claude fallback)                            │   │
│  │  ├─ Parse classification result                                     │   │
│  │  ├─ Store AIResponse record                                         │   │
│  │  └─ IF needs_reply: dispatch generate_ai_reply.delay()             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                 │                                           │
│                                 │                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  generate_ai_reply(email_id)                                        │   │
│  │  ├─ Fetch email context                                             │   │
│  │  ├─ Call LLM API for response generation                            │   │
│  │  ├─ Store generated reply                                           │   │
│  │  └─ Dispatch send_draft.delay()                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                 │                                           │
│                                 │                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  send_draft(email_id)                                               │   │
│  │  ├─ Fetch generated reply                                           │   │
│  │  ├─ Format Gmail draft message                                      │   │
│  │  ├─ Create draft via Gmail API                                      │   │
│  │  ├─ Store draft_id                                                  │   │
│  │  └─ Mark task as completed                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
                                 │ Draft created
                                 ▼
                     ┌────────────────────────┐
                     │   Gmail Drafts Folder  │
                     │  (Ready for user review)│
                     └────────────────────────┘
```

---

**Last Updated:** 2024-04-16  
**Version:** 1.0  
**Maintainers:** [INSERT TEAM]
