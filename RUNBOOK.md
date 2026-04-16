# Production Runbook 📚

This runbook provides operational procedures, troubleshooting guides, and maintenance tasks for AI Email Assistant in production environments.

## Table of Contents

- [Emergency Contacts](#emergency-contacts)
- [System Architecture Quick Reference](#system-architecture-quick-reference)
- [Common Operational Tasks](#common-operational-tasks)
- [Incident Response Procedures](#incident-response-procedures)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Maintenance Procedures](#maintenance-procedures)
- [Monitoring & Alerting](#monitoring--alerting)
- [Disaster Recovery](#disaster-recovery)
- [Security Incidents](#security-incidents)
- [Performance Tuning](#performance-tuning)
- [Deployment Procedures](#deployment-procedures)

## Emergency Contacts

### On-Call Rotation

| Role | Primary | Backup | Escalation |
|------|---------|--------|------------|
| Platform Engineer | [INSERT NAME] | [INSERT NAME] | [INSERT NAME] |
| Backend Engineer | [INSERT NAME] | [INSERT NAME] | [INSERT NAME] |
| DevOps | [INSERT NAME] | [INSERT NAME] | [INSERT NAME] |

### External Contacts

- **OpenAI Support:** support@openai.com
- **Google Cloud Support:** [SUPPORT TICKET LINK]
- **Database Provider:** [SUPPORT CONTACT]

### Communication Channels

- **Slack:** `#email-assistant-incidents`
- **Email:** [INSERT TEAM EMAIL]
- **Status Page:** [STATUS PAGE URL]

## System Architecture Quick Reference

### Service Locations

```
Production Environment:
- API: https://api.email-assistant.example.com
- Grafana: https://monitoring.email-assistant.example.com
- Sentry: https://sentry.io/email-assistant

Infrastructure:
- Database: [CLOUD SQL INSTANCE]
- Redis: [ELASTICACHE ENDPOINT]
- Workers: [KUBERNETES CLUSTER / ECS CLUSTER]
```

### Key Credentials

All credentials stored in `.env` file (production: use environment variables, not committed to git)

Required secrets:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `DATABASE_URL`
- `REDIS_URL`

### Service Dependencies

```
┌─────────────────────────────────────────────┐
│  Critical Dependencies (P0)                 │
├─────────────────────────────────────────────┤
│  Gmail API          - Email fetching        │
│  PostgreSQL         - Primary database      │
│  Redis              - Task queue            │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  High Priority Dependencies (P1)            │
├─────────────────────────────────────────────┤
│  OpenAI API         - Classification/Reply  │
│  Pub/Sub            - Webhook delivery      │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Medium Priority Dependencies (P2)          │
├─────────────────────────────────────────────┤
│  Anthropic API      - LLM fallback          │
│  Prometheus         - Metrics collection    │
│  Grafana            - Visualization         │
└─────────────────────────────────────────────┘
```

## Common Operational Tasks

### 1. Check System Health

**Command:**
```bash
# Check API health
curl https://api.email-assistant.example.com/api/health

# Check Celery workers
celery -A src.workers.celery_app inspect ping

# Check Redis connectivity
redis-cli -h $REDIS_HOST ping

# Check database connectivity
psql $DATABASE_URL -c "SELECT 1"
```

**Expected Output:**
```json
{
  "status": "healthy",
  "services": {
    "database": "connected",
    "redis": "connected",
    "celery_workers": 3
  }
}
```

### 2. View Active Tasks

**Command:**
```bash
# Active tasks by worker
celery -A src.workers.celery_app inspect active

# Queue depth
celery -A src.workers.celery_app inspect stats | jq '.[] | .total'

# Reserved tasks (prefetched but not started)
celery -A src.workers.celery_app inspect reserved
```

**Grafana Dashboard:**
- Navigate to "Email Pipeline" dashboard
- Check "Queue Depth" panel

### 3. Manual Email Processing

**Use Case:** Reprocess failed email or test specific email

**Command:**
```bash
# Via API
curl -X POST https://api.email-assistant.example.com/api/process-email \
  -H "Content-Type: application/json" \
  -d '{"email_id": "18f3a2b1c5d4e6f7", "force_reprocess": true}'

# Via Python shell
docker exec -it api python
>>> from src.services.worker_service import WorkerService
>>> import asyncio
>>> service = WorkerService()
>>> asyncio.run(service.process_classification("18f3a2b1c5d4e6f7"))
```

### 4. View Recent Logs

**Command:**
```bash
# API logs (last 100 lines)
docker logs --tail 100 api

# Worker logs
docker logs --tail 100 celery-worker

# Search for specific email
docker logs api | grep "email_id=18f3a2b1c5d4e6f7"

# Search for errors
docker logs api | grep '"level":"error"'
```

**Grafana Loki Query:**
```logql
{service="email-assistant"} 
  |= "error" 
  | json 
  | level="error"
  | line_format "{{.timestamp}} {{.message}}"
```

### 5. Restart Services

**API Server:**
```bash
# Docker Compose
docker-compose restart api

# Kubernetes
kubectl rollout restart deployment/email-assistant-api
```

**Celery Workers:**
```bash
# Docker Compose
docker-compose restart celery-worker

# Kubernetes
kubectl rollout restart deployment/celery-worker

# Graceful restart (finish current tasks)
docker exec celery-worker pkill -TERM celery
```

### 6. Scale Workers

**Docker Compose:**
```bash
docker-compose up -d --scale celery-worker=5
```

**Kubernetes:**
```bash
kubectl scale deployment/celery-worker --replicas=5
```

### 7. Clear Redis Queue

**⚠️ Warning:** This will lose pending tasks. Use only in emergencies.

```bash
# Clear specific queue
redis-cli -h $REDIS_HOST DEL celery:queue:default

# Clear all Celery data
redis-cli -h $REDIS_HOST KEYS "celery*" | xargs redis-cli -h $REDIS_HOST DEL
```

### 8. Database Queries

**Check recent emails:**
```sql
SELECT 
    id, 
    message_id, 
    sender, 
    subject, 
    processed, 
    created_at 
FROM emails 
ORDER BY created_at DESC 
LIMIT 10;
```

**Check failed tasks:**
```sql
SELECT 
    email_id, 
    task_name, 
    error_message, 
    created_at 
FROM failed_tasks 
WHERE resolved_at IS NULL 
ORDER BY created_at DESC;
```

**Pipeline statistics (last 24 hours):**
```sql
SELECT 
    ar.category,
    COUNT(*) as count,
    AVG(ar.confidence) as avg_confidence,
    AVG(EXTRACT(EPOCH FROM (pt.completed_at - pt.created_at))) as avg_duration_seconds
FROM ai_responses ar
JOIN processing_tasks pt ON pt.email_id = ar.email_id
WHERE pt.created_at > NOW() - INTERVAL '24 hours'
  AND pt.status = 'completed'
GROUP BY ar.category;
```

## Incident Response Procedures

### Severity Definitions

| Level | Definition | Response Time | Example |
|-------|------------|---------------|---------|
| **P0 - Critical** | Complete service outage | 5 minutes | All workers down, database unreachable |
| **P1 - High** | Degraded service | 15 minutes | High error rate, slow processing |
| **P2 - Medium** | Partial functionality loss | 1 hour | Single worker failure, fallback API active |
| **P3 - Low** | Minor issue | 4 hours | Monitoring alert, no user impact |

### Incident Response Steps

#### 1. Acknowledge & Assess

**Actions:**
- Post in `#email-assistant-incidents`: "Investigating [ISSUE]"
- Notify team via Slack or email
- Check Grafana dashboards for scope

**Questions to Answer:**
- What is the impact? (users affected, emails delayed)
- When did it start?
- Is this a new deployment?

#### 2. Triage & Stabilize

**Quick Wins:**
- Restart failed services
- Scale up workers if queue backing up
- Switch to fallback LLM if primary is down

**Collect Evidence:**
```bash
# Save logs
docker logs api > api-logs-$(date +%s).txt
docker logs celery-worker > worker-logs-$(date +%s).txt

# Save queue state
celery -A src.workers.celery_app inspect stats > celery-stats.json

# Database snapshot
psql $DATABASE_URL -c "SELECT * FROM failed_tasks WHERE created_at > NOW() - INTERVAL '1 hour'" > failed-tasks.csv
```

#### 3. Communicate

**Internal:**
- Status updates every 15 minutes in Slack
- Update incident ticket with findings

**External (if customer-facing):**
- Update status page
- Notify affected users if > 30 min downtime

#### 4. Resolve & Verify

**Verification Checklist:**
- [ ] All health checks passing
- [ ] Queue depth returning to normal
- [ ] Error rate below baseline
- [ ] End-to-end test successful

**Test Command:**
```bash
# Send test email and verify processing
curl -X POST https://api.email-assistant.example.com/api/process-email \
  -H "Content-Type: application/json" \
  -d '{"email_id": "test-email-id"}'
```

#### 5. Post-Mortem

**Required for P0/P1 incidents:**
- Root cause analysis
- Timeline of events
- Action items to prevent recurrence
- Runbook updates

**Template:** [LINK TO POST-MORTEM TEMPLATE]

## Troubleshooting Guide

### Issue: High Queue Depth

**Symptoms:**
- `celery_queue_length > 100`
- Emails taking > 5 minutes to process
- Alert: "HighQueueDepth"

**Diagnosis:**
```bash
# Check worker status
celery -A src.workers.celery_app inspect active
celery -A src.workers.celery_app inspect stats

# Check for stuck tasks
celery -A src.workers.celery_app inspect reserved
```

**Possible Causes:**
1. Workers crashed or stopped
2. LLM API rate limit hit
3. Database connection pool exhausted
4. Memory leak in worker process

**Resolution:**
```bash
# Quick fix: Scale up workers
docker-compose up -d --scale celery-worker=8

# If workers are stuck:
docker-compose restart celery-worker

# If rate limit issue:
# Check OpenAI dashboard, wait for reset, or enable Claude fallback
```

### Issue: Gmail API Quota Exceeded

**Symptoms:**
- Error: "User Rate Limit Exceeded" (error code 429)
- Alert: "GmailQuotaNearLimit"
- Processing stops for specific user

**Diagnosis:**
```bash
# Check quota usage in Google Cloud Console
gcloud logging read "resource.type=api AND protoPayload.methodName:gmail" \
  --limit 100 --format json | jq '[.[] | .protoPayload.status.code] | group_by(.) | map({code: .[0], count: length})'
```

**Resolution:**
```bash
# Short-term: Enable exponential backoff (already in code)
# Verify backoff is working:
docker logs celery-worker | grep "Rate limit"

# Long-term: Request quota increase
# Go to: https://console.cloud.google.com/apis/api/gmail.googleapis.com/quotas
```

**Prevention:**
- Implement Redis-based rate limiter
- Batch fetch emails during off-peak hours
- Cache email content to reduce API calls

### Issue: OAuth Token Expired

**Symptoms:**
- Error: "invalid_grant" or "Token has been expired or revoked"
- Gmail API calls fail with 401
- Unable to fetch emails

**Diagnosis:**
```bash
# Check token.json validity
cat token.json | jq '.expiry'

# Check refresh token exists
cat token.json | jq '.refresh_token'
```

**Resolution:**
```bash
# Re-run OAuth flow
python scripts/oauth_flow.py

# Verify new token
cat token.json | jq '.token'

# Restart workers to pick up new token
docker-compose restart celery-worker
```

**Prevention:**
- Implement proactive token refresh (before expiry)
- Monitor token refresh failures
- Alert on missing refresh_token

### Issue: Workers Not Processing Tasks

**Symptoms:**
- Tasks stuck in "pending" state
- `celery_worker_heartbeat` metric = 0
- No worker logs appearing

**Diagnosis:**
```bash
# Check worker processes
docker ps | grep celery-worker

# Check worker logs
docker logs celery-worker --tail 50

# Verify Redis connectivity from worker
docker exec celery-worker redis-cli -h redis ping
```

**Possible Causes:**
1. Worker container crashed (OOM, exception)
2. Redis connection lost
3. Database connection pool exhausted
4. Deadlock in task code

**Resolution:**
```bash
# Restart workers
docker-compose restart celery-worker

# If OOM issue, increase memory limit in docker-compose.yml:
# mem_limit: 2g

# Check for deadlocks in database
psql $DATABASE_URL -c "SELECT * FROM pg_stat_activity WHERE state = 'active'"
```

### Issue: LLM API Failures

**Symptoms:**
- Error: "RateLimitError" or "ServiceUnavailable"
- Tasks retrying repeatedly
- Classification/reply generation failing

**Diagnosis:**
```bash
# Check OpenAI status
curl https://status.openai.com/api/v2/status.json

# Check recent LLM errors
docker logs celery-worker | grep -i "openai\|anthropic" | grep -i error

# Verify API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Resolution:**
```bash
# If rate limit: Wait for reset (check OpenAI dashboard)

# If outage: Enable Claude fallback
# Edit .env: USE_ANTHROPIC_FALLBACK=true
docker-compose restart celery-worker

# If API key invalid: Rotate key
# Update secret in Vault/Secrets Manager
# Restart workers
```

### Issue: Database Connection Pool Exhausted

**Symptoms:**
- Error: "FATAL: sorry, too many clients already"
- API returns 500 errors
- Workers hang on database operations

**Diagnosis:**
```sql
-- Check active connections
SELECT count(*) FROM pg_stat_activity;

-- Check connection pool stats
SELECT 
    pid,
    usename,
    application_name,
    state,
    query_start,
    state_change
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
```

**Resolution:**
```bash
# Short-term: Kill idle connections
psql $DATABASE_URL -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND state_change < NOW() - INTERVAL '5 minutes'"

# Long-term: Increase pool size in src/config.py
# SQLALCHEMY_POOL_SIZE = 30
# SQLALCHEMY_MAX_OVERFLOW = 20

# Or deploy pgbouncer
```

### Issue: High Memory Usage

**Symptoms:**
- Worker containers restarting (OOMKilled)
- Slow performance
- Alert: "HighMemoryUsage"

**Diagnosis:**
```bash
# Check memory usage
docker stats --no-stream

# Check for memory leaks in Python
docker exec celery-worker python -c "
import tracemalloc
tracemalloc.start()
# Run some tasks
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
"
```

**Resolution:**
```bash
# Restart workers to clear memory
docker-compose restart celery-worker

# Reduce worker concurrency
# Edit docker-compose.yml:
# command: celery -A src.workers.celery_app worker --concurrency=2

# Enable worker max-tasks-per-child (restart after N tasks)
# Edit src/workers/celery_app.py:
# celery_app.conf.worker_max_tasks_per_child = 100
```

### Issue: Duplicate Email Processing

**Symptoms:**
- Same email processed multiple times
- Multiple AI responses for single email
- Duplicate entries in database

**Diagnosis:**
```sql
-- Find duplicate processing
SELECT 
    message_id, 
    COUNT(*) as count 
FROM emails 
GROUP BY message_id 
HAVING COUNT(*) > 1;
```

**Possible Causes:**
- Pub/Sub webhook fired multiple times
- Deduplication check race condition
- Worker processing same task twice

**Resolution:**
```sql
-- Add unique constraint (if not exists)
ALTER TABLE emails ADD CONSTRAINT unique_message_id UNIQUE (message_id);

-- Clean up duplicates
DELETE FROM emails 
WHERE id NOT IN (
    SELECT MIN(id) 
    FROM emails 
    GROUP BY message_id
);
```

**Prevention:**
- Implement Redis-based distributed lock
- Use database transaction isolation level SERIALIZABLE
- Add idempotency key to tasks

## Maintenance Procedures

### Weekly Maintenance

#### 1. Database Maintenance

**Vacuum & Analyze:**
```sql
-- Run during low-traffic hours
VACUUM ANALYZE emails;
VACUUM ANALYZE processing_tasks;
VACUUM ANALYZE ai_responses;
VACUUM ANALYZE failed_tasks;
```

**Check Table Bloat:**
```sql
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

#### 2. Failed Task Review

**Query:**
```sql
SELECT 
    id,
    email_id,
    task_name,
    error_message,
    retry_count,
    created_at
FROM failed_tasks
WHERE resolved_at IS NULL
ORDER BY created_at DESC
LIMIT 20;
```

**Actions:**
- Investigate root cause
- Retry manually if transient error
- Mark as resolved if permanent issue

**Mark as Resolved:**
```sql
UPDATE failed_tasks 
SET resolved_at = NOW() 
WHERE id = [TASK_ID];
```

#### 3. Log Rotation

**Command:**
```bash
# Compress old logs
find /var/log/email-assistant -name "*.log" -mtime +7 -exec gzip {} \;

# Delete logs older than 30 days
find /var/log/email-assistant -name "*.log.gz" -mtime +30 -delete
```

### Monthly Maintenance

#### 1. Gmail Watch Renewal

**Status:** Automated via Celery Beat (every 6 days)

**Manual Renewal:**
```bash
python scripts/setup_watch.py
```

**Verification:**
```bash
# Check watch expiration
psql $DATABASE_URL -c "SELECT * FROM watch_subscriptions ORDER BY created_at DESC LIMIT 1"
```

#### 2. Certificate Renewal

**Let's Encrypt (if applicable):**
```bash
certbot renew --dry-run
```

#### 3. Dependency Updates

**Check for updates:**
```bash
pip list --outdated
```

**Security updates only:**
```bash
pip install --upgrade $(pip list --outdated | grep -i security | awk '{print $1}')
```

#### 4. Database Backup Verification

**Test restore:**
```bash
# Restore to test database
pg_restore -d email_assistant_test /path/to/backup.dump

# Verify data
psql email_assistant_test -c "SELECT COUNT(*) FROM emails"
```

### Quarterly Maintenance

#### 1. Performance Review

**Metrics to Review:**
- API latency trends (p95, p99)
- Database query performance
- Worker throughput
- Error rates

**Actions:**
- Optimize slow queries (use EXPLAIN ANALYZE)
- Add indexes where needed
- Review and update capacity plan

#### 2. Security Audit

**Checklist:**
- [ ] Rotate API keys (OpenAI, Anthropic, Gmail)
- [ ] Review OAuth token security
- [ ] Update dependencies with security patches
- [ ] Review file permissions on `.env` and `token.json`
- [ ] Check for exposed secrets in logs

#### 3. Disaster Recovery Drill

**Steps:**
1. Simulate database failure
2. Restore from backup
3. Verify data integrity
4. Document recovery time

## Monitoring & Alerting

### Critical Alerts

#### 1. No Workers Available

**Alert Rule:**
```promql
sum(up{job="celery-worker"}) == 0
```

**Response:**
1. Check worker container status: `docker ps`
2. Review worker logs: `docker logs celery-worker`
3. Restart workers: `docker-compose restart celery-worker`
4. If issue persists, check Redis connectivity

#### 2. High Error Rate

**Alert Rule:**
```promql
rate(http_requests_total{status=~"5.."}[5m]) > 0.1
```

**Response:**
1. Check API logs for error patterns
2. Verify database connectivity
3. Check external API status (Gmail, OpenAI)
4. Review recent deployments (rollback if needed)

#### 3. Gmail Quota Near Limit

**Alert Rule:**
```promql
gmail_api_quota_used / gmail_api_quota_limit > 0.8
```

**Response:**
1. Check current quota usage in Google Cloud Console
2. Reduce polling frequency (if applicable)
3. Enable caching for repeated requests
4. Request quota increase if sustained high usage

### Dashboard Monitoring

**Daily Checks:**
- System Health dashboard (9:00 AM)
- Email Pipeline metrics (5:00 PM)
- Error rate trends

**Weekly Review:**
- Capacity utilization
- Cost trends (LLM API usage)
- Failed task analysis

## Disaster Recovery

### Backup Strategy

**Database Backups:**
- Frequency: Every 6 hours
- Retention: 30 days
- Location: [S3 BUCKET / CLOUD STORAGE]

**Verify Backup:**
```bash
aws s3 ls s3://email-assistant-backups/postgres/ --recursive | tail
```

**Configuration Backups:**
- Git repository: [REPO URL]
- Environment files: Stored securely (not in git)

### Recovery Procedures

#### Scenario 1: Database Failure

**Recovery Time Objective (RTO):** 30 minutes  
**Recovery Point Objective (RPO):** 6 hours

**Steps:**
1. Spin up new database instance
2. Restore from latest backup:
   ```bash
   pg_restore -d email_assistant /path/to/backup.dump
   ```
3. Update connection string in .env
4. Restart all services
5. Verify data integrity

#### Scenario 2: Complete Infrastructure Failure

**RTO:** 2 hours  
**RPO:** 6 hours

**Steps:**
1. Deploy infrastructure from IaC (Terraform/CloudFormation)
2. Restore database from backup
3. Deploy application containers
4. Restore configuration from Git
5. Re-initialize Gmail watch subscription
6. Run end-to-end test

#### Scenario 3: Data Corruption

**Steps:**
1. Stop all write operations
2. Identify corruption scope
3. Restore affected tables from backup:
   ```bash
   pg_dump -t emails backup.dump | psql $DATABASE_URL
   ```
4. Verify data consistency
5. Resume operations

### Backup Restoration Test

**Schedule:** Quarterly

**Procedure:**
1. Create test environment
2. Restore production backup
3. Run data validation queries
4. Document any issues
5. Update runbook with learnings

## Security Incidents

### Types of Security Incidents

1. **Unauthorized Access**: Login attempts, credential leaks
2. **Data Breach**: Email content exposure
3. **API Key Compromise**: OpenAI/Gmail keys stolen
4. **DDoS Attack**: Webhook endpoint targeted

### Response Procedures

#### 1. Confirm Incident

**Questions:**
- What is the nature of the incident?
- When was it detected?
- What is the potential impact?

**Immediate Actions:**
- Isolate affected systems
- Preserve evidence (logs, snapshots)
- Notify security team

#### 2. Contain Incident

**For API Key Compromise:**
```bash
# Revoke compromised key immediately
# OpenAI: https://platform.openai.com/account/api-keys
# Gmail: https://console.cloud.google.com/apis/credentials

# Generate new key and update .env file
# In production: update environment variables on hosting platform

# Restart services
docker-compose restart
```

**For Unauthorized Access:**
```bash
# Kill active sessions
psql $DATABASE_URL -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = '[COMPROMISED_USER]'"

# Change passwords
# Review audit logs
```

#### 3. Investigate

**Collect Evidence:**
```bash
# API access logs
docker logs api --since "2024-04-16T10:00:00" > access-logs.txt

# Authentication attempts
grep "authentication" /var/log/email-assistant/*.log

# Database audit trail
psql $DATABASE_URL -c "SELECT * FROM audit_log WHERE timestamp > '[INCIDENT_TIME]'"
```

#### 4. Recover & Harden

**Actions:**
- Restore from clean backup if data corruption
- Implement additional security controls
- Update WAF rules
- Enable 2FA for all admin accounts

#### 5. Post-Incident Review

**Required Documentation:**
- Timeline of events
- Root cause analysis
- Security improvements implemented
- Runbook updates

## Performance Tuning

### Database Optimization

**Identify Slow Queries:**
```sql
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

**Add Indexes:**
```sql
-- Example: Speed up email lookups by message_id
CREATE INDEX CONCURRENTLY idx_emails_message_id ON emails(message_id);

-- Verify index usage
EXPLAIN ANALYZE SELECT * FROM emails WHERE message_id = 'abc123';
```

**Connection Pooling:**
```python
# src/config.py
SQLALCHEMY_POOL_SIZE = 20
SQLALCHEMY_MAX_OVERFLOW = 10
SQLALCHEMY_POOL_TIMEOUT = 30
SQLALCHEMY_POOL_RECYCLE = 3600
```

### Worker Optimization

**Tune Concurrency:**
```bash
# Test different concurrency levels
celery -A src.workers.celery_app worker --concurrency=2  # Low
celery -A src.workers.celery_app worker --concurrency=8  # High

# Monitor memory and CPU
docker stats celery-worker
```

**Optimize Task Prefetching:**
```python
# src/workers/celery_app.py
worker_prefetch_multiplier = 1  # Lower for long tasks
worker_prefetch_multiplier = 4  # Higher for short tasks
```

### Redis Optimization

**Monitor Memory:**
```bash
redis-cli INFO memory

# Check keyspace
redis-cli INFO keyspace
```

**Set Maxmemory Policy:**
```bash
# In redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

### API Optimization

**Enable Response Caching:**
```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url("redis://localhost")
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")

@app.get("/api/email/{email_id}")
@cache(expire=60)  # Cache for 60 seconds
async def get_email(email_id: str):
    pass
```

## Deployment Procedures

### Pre-Deployment Checklist

- [ ] All tests passing in CI
- [ ] Database migrations tested
- [ ] Rollback plan prepared
- [ ] Change notification sent
- [ ] Monitoring dashboards open

### Deployment Steps

#### 1. Database Migration (if required)

```bash
# Backup database first
pg_dump $DATABASE_URL > backup-$(date +%s).sql

# Run migration
alembic upgrade head

# Verify migration
psql $DATABASE_URL -c "\dt"
```

#### 2. Deploy API

**Blue-Green Deployment:**
```bash
# Deploy new version (green)
docker-compose -f docker-compose.prod.yml up -d --no-deps --build api-green

# Health check
curl https://api-green.email-assistant.example.com/api/health

# Switch traffic (update load balancer)
# ...

# If successful, stop old version (blue)
docker-compose -f docker-compose.prod.yml stop api-blue
```

#### 3. Deploy Workers

**Rolling Update:**
```bash
# Scale up new version
docker-compose up -d --scale celery-worker-new=3

# Wait for new workers to start processing
sleep 30

# Scale down old version
docker-compose up -d --scale celery-worker-old=0
```

#### 4. Verify Deployment

```bash
# Check health
curl https://api.email-assistant.example.com/api/health

# Process test email
curl -X POST https://api.email-assistant.example.com/api/process-email \
  -H "Content-Type: application/json" \
  -d '{"email_id": "test-email-123"}'

# Monitor metrics for 15 minutes
# Check Grafana for error rate, latency
```

### Rollback Procedure

**If deployment fails:**

```bash
# Revert database migration
alembic downgrade -1

# Revert to previous container version
docker-compose -f docker-compose.prod.yml up -d --no-deps api:previous-tag

# Clear Redis cache to prevent stale data
redis-cli FLUSHDB
```

### Post-Deployment

- [ ] Verify metrics returning to baseline
- [ ] Check error logs for new issues
- [ ] Monitor for 1 hour after deployment
- [ ] Update deployment log

---

## Appendix

### Useful Commands Cheatsheet

```bash
# Health checks
curl /api/health
celery inspect ping
redis-cli ping
psql -c "SELECT 1"

# Logs
docker logs api --tail 100 -f
docker logs celery-worker --tail 100 -f

# Metrics
curl /api/metrics
celery inspect stats

# Database
psql $DATABASE_URL
\dt                                    # List tables
SELECT COUNT(*) FROM emails;           # Count emails

# Redis
redis-cli
KEYS celery*                           # List Celery keys
LLEN celery:queue:default              # Queue length

# Scaling
docker-compose up -d --scale celery-worker=5
kubectl scale deployment/celery-worker --replicas=5
```

### Contact Information

**Team Email:** [INSERT TEAM EMAIL]  
**Team Slack:** `#email-assistant`  
**Incident Response:** `#email-assistant-incidents`

---

**Last Updated:** 2024-04-16  
**Version:** 1.0  
**Next Review:** 2024-07-16
