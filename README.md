# AI Email Assistant 🤖📧

> Intelligent Gmail automation with AI-powered email classification, response generation, and draft creation using FastAPI, Celery, and LLM integration.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-green)
![License](https://img.shields.io/badge/license-[INSERT%20LICENSE]-blue)
![Build Status](https://img.shields.io/badge/build-[INSERT%20STATUS]-brightgreen)

## 🚀 Overview

AI Email Assistant is a production-grade email automation system that leverages Large Language Models to intelligently process incoming Gmail messages. The system automatically classifies emails, generates contextually relevant AI-powered responses, and creates draft replies — all while maintaining high reliability through distributed task processing and comprehensive monitoring.

**Key Capabilities:**
- Real-time email processing via Google Cloud Pub/Sub webhooks
- AI-powered email classification (needs_reply, spam, informational)
- Context-aware response generation using OpenAI GPT-4 or Anthropic Claude
- Automatic draft creation in Gmail
- Distributed task processing with Celery workers
- Production-ready observability stack (Prometheus, Grafana, Loki)

## 📋 Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Monitoring](#monitoring)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## 🏗 Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Gmail     │─────▶│  Pub/Sub     │─────▶│   FastAPI   │
│   Inbox     │      │  Webhook     │      │   Webhook   │
└─────────────┘      └──────────────┘      └──────┬──────┘
                                                   │
                                                   ▼
                                           ┌───────────────┐
                                           │  PostgreSQL   │
                                           │  (Task Queue) │
                                           └───────┬───────┘
                                                   │
                          ┌────────────────────────┼─────────────────────────┐
                          │                        │                         │
                          ▼                        ▼                         ▼
                    ┌──────────┐           ┌──────────┐            ┌──────────┐
                    │  Celery  │           │  Celery  │            │  Celery  │
                    │  Worker  │           │  Worker  │            │  Worker  │
                    │ (classify)│           │ (generate)│           │  (send)  │
                    └────┬─────┘           └────┬─────┘            └────┬─────┘
                         │                      │                       │
                         └──────────────┬───────┴───────────────────────┘
                                        ▼
                              ┌─────────────────┐
                              │   OpenAI API    │
                              │  Claude API     │
                              │   Gmail API     │
                              └─────────────────┘
```

**Processing Pipeline:**

1. **Webhook Reception**: Gmail sends notification via Pub/Sub to FastAPI endpoint
2. **Task Creation**: FastAPI validates webhook, stores email metadata in PostgreSQL
3. **Classification**: Celery worker fetches email content, sends to LLM for categorization
4. **Response Generation**: If email needs reply, separate worker generates AI response
5. **Draft Creation**: Final worker creates Gmail draft using generated content
6. **Monitoring**: All steps tracked via Prometheus metrics, logs aggregated in Loki

## 🛠 Tech Stack

**Backend & API:**
- [FastAPI](https://fastapi.tiangolo.com/) 0.104+ — Async web framework
- [Python](https://python.org) 3.11+ — Core language
- [Uvicorn](https://www.uvicorn.org/) — ASGI server

**Database & Storage:**
- [PostgreSQL](https://postgresql.org) 15+ — Primary database with SQLAlchemy 2.0 ORM
- [Alembic](https://alembic.sqlalchemy.org/) — Database migrations
- [Redis](https://redis.io) 7+ — Message broker and result backend (AOF persistence)

**Task Processing:**
- [Celery](https://docs.celeryq.dev/) 5.3+ — Distributed task queue
- Retry logic with exponential backoff
- Dead-letter queue for failed tasks

**AI & External APIs:**
- [OpenAI API](https://platform.openai.com/) — GPT-4 for email processing (primary)
- [Anthropic Claude API](https://anthropic.com) — Fallback LLM provider
- [Gmail API](https://developers.google.com/gmail/api) — Email fetching and draft creation
- [Google Cloud Pub/Sub](https://cloud.google.com/pubsub) — Real-time webhook notifications

**Observability:**
- [Prometheus](https://prometheus.io/) — Metrics collection
- [Grafana](https://grafana.com/) — Visualization and dashboards
- [Loki](https://grafana.com/oss/loki/) — Log aggregation
- [Promtail](https://grafana.com/docs/loki/latest/clients/promtail/) — Log shipping
- [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) — Alert routing
- [structlog](https://www.structlog.org/) — Structured JSON logging

**Infrastructure:**
- [Docker](https://docker.com) & Docker Compose — Containerization
- Pre-commit hooks with [Ruff](https://github.com/astral-sh/ruff) — Code quality

## ✨ Features

### Core Functionality
- ✅ **Real-time Email Processing** — Webhook-triggered immediate processing
- ✅ **AI Classification** — Automatic categorization (needs_reply, informational, spam)
- ✅ **Context-Aware Responses** — LLM analyzes email content and generates replies
- ✅ **Gmail Draft Creation** — Automatic draft creation in Gmail UI
- ✅ **Distributed Workers** — Celery-based horizontal scaling

### Reliability & Error Handling
- ✅ **Exponential Backoff** — Automatic retry on API failures (5 attempts)
- ✅ **Dead-Letter Queue** — Failed tasks stored in `failed_tasks` table
- ✅ **Deduplication** — Prevents duplicate processing via email_id tracking
- ✅ **Gmail Watch Renewal** — Scheduled job maintains Pub/Sub subscription (every 6 days)
- ✅ **Circuit Breaker** — Fallback to Claude on OpenAI outage

### Monitoring & Observability
- ✅ **Custom Metrics** — Task duration, API latency, queue depth tracking
- ✅ **Structured Logs** — JSON logs with correlation IDs across services
- ✅ **Pre-built Dashboards** — Grafana dashboards for system health
- ✅ **Alerting** — Configurable alerts for quota exhaustion, worker starvation

### Security
- ✅ **OAuth 2.0 Integration** — Secure Gmail authentication
- ✅ **Rate Limiting** — Protection against webhook abuse
- ✅ **Input Sanitization** — HTML stripping with BeautifulSoup
- ✅ **Pub/Sub Token Verification** — OIDC token validation

## 📦 Prerequisites

- **Python** 3.11 or higher
- **Docker** 20.10+ and Docker Compose 2.0+
- **Gmail Account** with API access enabled
- **Google Cloud Project** with Pub/Sub API enabled
- **OpenAI API Key** or **Anthropic API Key**

Optional for production:
- PostgreSQL 15+ (if not using Docker)
- Redis 7+ (if not using Docker)

## 🔧 Installation

### 1. Clone Repository

```bash
git clone https://github.com/[YOUR_USERNAME]/ai-email-assistant.git
cd ai-email-assistant
```

### 2. Gmail API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project or select existing
3. Enable **Gmail API** and **Cloud Pub/Sub API**
4. Create OAuth 2.0 credentials:
   - Application type: **Desktop app**
   - Download `credentials.json` → place in project root
5. Set up Pub/Sub topic and subscription:
   ```bash
   gcloud pubsub topics create gmail-notifications
   gcloud pubsub subscriptions create gmail-push-subscription \
     --topic=gmail-notifications \
     --push-endpoint=https://[YOUR_DOMAIN]/api/webhook/gmail
   ```

### 3. Configure OAuth Flow

```bash
python scripts/oauth_flow.py
```

This generates `token.json` with refresh token. Follow browser prompts to authorize.

### 4. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/email_assistant

# Redis
REDIS_URL=redis://redis:6379/0

# Gmail API
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_USER_EMAIL=your-email@gmail.com

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...  # Optional fallback
USE_ANTHROPIC_FALLBACK=true

# Google Cloud
PUBSUB_PROJECT_ID=your-gcp-project-id
PUBSUB_TOPIC_NAME=gmail-notifications
PUBSUB_SUBSCRIPTION_NAME=gmail-push-subscription

# Application
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### 5. Start Services

```bash
docker-compose up --build
```

Services will be available at:
- **FastAPI API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090

### 6. Run Migrations

```bash
docker-compose exec api alembic upgrade head
```

### 7. Set Up Gmail Watch

```bash
docker-compose exec api python scripts/setup_watch.py
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | — | ✅ |
| `REDIS_URL` | Redis connection string | — | ✅ |
| `GMAIL_CLIENT_ID` | OAuth 2.0 client ID | — | ✅ |
| `GMAIL_CLIENT_SECRET` | OAuth 2.0 client secret | — | ✅ |
| `GMAIL_USER_EMAIL` | Target Gmail account | — | ✅ |
| `OPENAI_API_KEY` | OpenAI API key | — | ✅ |
| `ANTHROPIC_API_KEY` | Anthropic API key (fallback) | — | ❌ |
| `USE_ANTHROPIC_FALLBACK` | Enable Claude fallback | `false` | ❌ |
| `PUBSUB_PROJECT_ID` | GCP project ID | — | ✅ |
| `PUBSUB_TOPIC_NAME` | Pub/Sub topic | `gmail-notifications` | ✅ |
| `LOG_LEVEL` | Logging verbosity | `INFO` | ❌ |
| `CELERY_CONCURRENCY` | Worker concurrency | `4` | ❌ |

### LLM Configuration

Edit `src/services/ai_service.py` to customize:

```python
CLASSIFICATION_PROMPT = """
Analyze the email and categorize it:
- needs_reply: Requires response
- informational: FYI only
- spam: Unsolicited content
"""

REPLY_GENERATION_PROMPT = """
Generate a professional response to:
Subject: {subject}
From: {sender}
Content: {body}
"""
```

### Rate Limiting

Modify `src/utils/limiter.py`:

```python
gmail_limiter = RateLimiter(
    max_requests=50,  # Max requests per window
    window_seconds=60  # Time window in seconds
)
```

## 🚀 Usage

### Manual Email Processing

Trigger processing for specific email:

```bash
curl -X POST http://localhost:8000/api/process-email \
  -H "Content-Type: application/json" \
  -d '{"email_id": "18f3a2b1c5d4e6f7"}'
```

### View Processing Status

```bash
curl http://localhost:8000/api/task-status/{task_id}
```

Response:

```json
{
  "task_id": "abc-123",
  "email_id": "18f3a2b1c5d4e6f7",
  "status": "completed",
  "stage": "draft_created",
  "created_at": "2026-04-16T10:30:00Z",
  "completed_at": "2026-04-16T10:30:15Z",
  "ai_response": {
    "category": "needs_reply",
    "confidence": 0.95,
    "generated_reply": "Thank you for your inquiry..."
  }
}
```

### Failed Tasks

Query dead-letter queue:

```bash
curl http://localhost:8000/api/failed-tasks
```

## 📊 Monitoring

### Grafana Dashboards

Access pre-configured dashboards at http://localhost:3000:

1. **System Overview**
   - API request rate and latency (p50, p95, p99)
   - Celery queue depth
   - Worker health status

2. **Email Pipeline**
   - Emails processed per hour
   - Classification distribution
   - AI response time

3. **External APIs**
   - Gmail API quota usage
   - OpenAI API latency
   - Error rate by provider

### Key Metrics

```promql
# Queue depth alert
celery_queue_length{queue="default"} > 100

# Gmail quota usage
gmail_api_quota_used / gmail_api_quota_limit > 0.8

# Worker starvation
rate(celery_worker_heartbeat[5m]) == 0
```

### Logs

View structured logs:

```bash
docker-compose logs -f api
docker-compose logs -f celery-worker
```

Query Loki via Grafana Explore:

```logql
{service="email-assistant"} |= "error" | json
```

## 📚 API Documentation

Interactive API docs available at http://localhost:8000/docs

### Core Endpoints

#### POST `/api/webhook/gmail`
Receives Gmail Pub/Sub notifications.

**Request:**
```json
{
  "message": {
    "data": "base64_encoded_payload",
    "messageId": "123456"
  }
}
```

**Response:** `204 No Content`

#### GET `/api/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "celery_workers": 3
}
```

#### GET `/api/metrics`
Prometheus metrics endpoint.

## 📁 Project Structure

```
ai-email-assistant/
├── docker-compose.yml          # Service orchestration
├── Dockerfile                  # Application container
├── alembic.ini                 # Database migration config
├── pyproject.toml              # Python dependencies
├── .env.example                # Environment template
│
├── monitoring/                 # Observability stack
│   ├── prometheus/
│   │   └── prometheus.yml      # Scrape configuration
│   ├── grafana/
│   │   ├── dashboards/         # Pre-built dashboards
│   │   └── datasources/        # Data source configs
│   ├── loki/
│   │   └── loki-config.yml
│   ├── promtail/
│   │   └── promtail-config.yml
│   └── alertmanager/
│       └── alertmanager.yml
│
├── scripts/
│   ├── oauth_flow.py           # OAuth token generation
│   └── setup_watch.py          # Gmail watch initialization
│
└── src/
    ├── main.py                 # FastAPI application
    ├── config.py               # Settings management
    ├── dependencies.py         # Dependency injection
    │
    ├── alembic/                # Database migrations
    │   └── versions/
    │       ├── 9617af0fa031_initial_schema.py
    │       └── [future migrations]
    │
    ├── api/                    # HTTP layer
    │   ├── router.py           # Route registration
    │   └── webhook.py          # Pub/Sub webhook handler
    │
    ├── models/                 # SQLAlchemy ORM
    │   ├── base.py             # Base model class
    │   ├── email.py            # Email metadata
    │   ├── task.py             # Processing tasks
    │   ├── response.py         # AI responses
    │   └── failed_task.py      # Dead-letter queue
    │
    ├── schemas/                # Pydantic schemas
    │   ├── webhook.py          # Pub/Sub payload
    │   └── ai.py               # AI request/response
    │
    ├── services/               # Business logic
    │   ├── email_service.py    # Email CRUD operations
    │   ├── ai_service.py       # LLM integration
    │   ├── webhook_service.py  # Webhook processing
    │   ├── watch_service.py    # Gmail watch management
    │   ├── worker_service.py   # Celery task orchestration
    │   └── storage_service.py  # File storage abstraction
    │
    ├── utils/                  # Shared utilities
    │   ├── gmail.py            # Gmail API client
    │   ├── limiter.py          # Rate limiting
    │   ├── logging.py          # Structured logging
    │   ├── metrics.py          # Prometheus metrics
    │   ├── pubsub.py           # Pub/Sub utilities
    │   └── sanitizer.py        # HTML sanitization
    │
    └── workers/                # Celery tasks
        ├── celery_app.py       # Celery configuration
        ├── tasks.py            # Task definitions
        └── callbacks.py        # Task failure handlers
```

## 🔨 Development

### Setup Development Environment

```bash
# Install pre-commit hooks
pre-commit install

# Run linting
ruff check src/
ruff format src/

# Type checking
mypy src/
```

### Database Migrations

Create new migration:

```bash
alembic revision --autogenerate -m "description"
```

Apply migrations:

```bash
alembic upgrade head
```

Rollback:

```bash
alembic downgrade -1
```

### Adding New Tasks

1. Define task in `src/workers/tasks.py`:
   ```python
   @celery_app.task(bind=True, autoretry_for=(Exception,))
   def my_new_task(self, email_id: str):
       # Task logic
       pass
   ```

2. Register in pipeline in `src/services/worker_service.py`

3. Add tests in `tests/workers/test_my_task.py`

## 🧪 Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific test file
pytest tests/test_ai_service.py

# Integration tests
pytest tests/integration/ -v
```

**Coverage Target:** >80% (enforced in CI)

## 🚢 Deployment

### Production Checklist

- [ ] Environment variables properly configured (not committed to git)
- [ ] `ENVIRONMENT=production` set
- [ ] Rate limiting enabled
- [ ] CORS restricted to production domains
- [ ] PostgreSQL automated backups configured
- [ ] Redis persistence (AOF) enabled
- [ ] Monitoring alerts configured
- [ ] Gmail watch renewal cron job scheduled
- [ ] TLS certificates for webhook endpoint
- [ ] Horizontal scaling tested (multiple workers)

### Docker Production Build

```bash
docker build -t ai-email-assistant:latest .
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Cloud Deployment

**Google Cloud Run** (recommended for webhook):

```bash
gcloud run deploy email-assistant \
  --image gcr.io/[PROJECT_ID]/email-assistant \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars DATABASE_URL=[CLOUD_SQL_URL]
```

**AWS ECS/Fargate:**

[INSERT AWS-SPECIFIC DEPLOYMENT INSTRUCTIONS]

## 🐛 Troubleshooting

### Common Issues

**1. Webhook Not Receiving Events**

Check Pub/Sub subscription status:
```bash
gcloud pubsub subscriptions describe gmail-push-subscription
```

Verify webhook endpoint is publicly accessible and returns 200.

**2. OAuth Token Expired**

Re-run OAuth flow:
```bash
python scripts/oauth_flow.py
```

Check `token.json` has valid `refresh_token`.

**3. Celery Workers Not Picking Up Tasks**

Check Redis connectivity:
```bash
redis-cli -h localhost ping
```

View worker logs:
```bash
docker-compose logs celery-worker
```

Verify queue:
```bash
celery -A src.workers.celery_app inspect active
```

**4. Gmail API Quota Exceeded**

Check quota in [Google Cloud Console](https://console.cloud.google.com/apis/api/gmail.googleapis.com/quotas).

Implement exponential backoff (already included in `gmail.py`).

**5. Database Connection Pool Exhausted**

Increase pool size in `config.py`:
```python
SQLALCHEMY_POOL_SIZE = 20
SQLALCHEMY_MAX_OVERFLOW = 10
```

### Debug Mode

Enable verbose logging:

```bash
export LOG_LEVEL=DEBUG
docker-compose restart api celery-worker
```

### Health Checks

```bash
# API health
curl http://localhost:8000/api/health

# Celery workers
celery -A src.workers.celery_app inspect ping

# Database
psql $DATABASE_URL -c "SELECT 1"
```

## 🤝 Contributing

Contributions welcome! Please follow these steps:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

**Code Standards:**
- Use Ruff for linting and formatting
- Add tests for new features (pytest)
- Update documentation for user-facing changes
- Follow semantic commit messages

## 📄 License

[INSERT LICENSE TYPE] — See [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) team for excellent async framework
- [Celery](https://docs.celeryq.dev/) maintainers
- OpenAI and Anthropic for LLM APIs
- Google for Gmail API and Pub/Sub

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/[USERNAME]/ai-email-assistant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/[USERNAME]/ai-email-assistant/discussions)
- **Email**: [INSERT SUPPORT EMAIL]

## 🗺 Roadmap

**Completed:**
- ✅ Core email classification pipeline
- ✅ AI response generation
- ✅ Gmail draft creation
- ✅ Monitoring stack

**In Progress:**
- 🚧 Multi-user support
- 🚧 Web UI dashboard

**Planned:**
- [ ] Fine-tuned classification model
- [ ] Slack/Teams integration
- [ ] Email templates library
- [ ] A/B testing for prompts
- [ ] Analytics dashboard

---

**Built with ❤️ using FastAPI, Celery, and LLMs**
