# Contributing to AI Email Assistant 🤝

Thank you for your interest in contributing to AI Email Assistant! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Development Environment Setup](#development-environment-setup)
- [Architecture Guidelines](#architecture-guidelines)
- [Documentation Standards](#documentation-standards)

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors, regardless of experience level, gender identity, sexual orientation, disability, personal appearance, body size, race, ethnicity, age, religion, or nationality.

### Expected Behavior

- Use welcoming and inclusive language
- Respect differing viewpoints and experiences
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other community members

### Unacceptable Behavior

- Trolling, insulting/derogatory comments, personal or political attacks
- Public or private harassment
- Publishing others' private information without permission
- Other conduct which could reasonably be considered inappropriate

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- Python 3.11 or higher installed
- Docker and Docker Compose
- Git configured with your name and email
- A GitHub account
- Gmail API credentials (for testing)
- OpenAI or Anthropic API key (for testing)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-email-assistant.git
   cd ai-email-assistant
   ```

3. Add upstream remote:
   ```bash
   git remote add upstream https://github.com/ORIGINAL_OWNER/ai-email-assistant.git
   ```

4. Create a branch for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### 1. Set Up Development Environment

```bash
# Copy environment template
cp .env.example .env

# Install pre-commit hooks
pre-commit install

# Start services
docker-compose up -d

# Run migrations
docker-compose exec api alembic upgrade head
```

### 2. Make Your Changes

- Write clean, documented code
- Add tests for new functionality
- Update documentation as needed
- Follow the coding standards below

### 3. Run Quality Checks

```bash
# Linting
ruff check src/

# Formatting
ruff format src/

# Type checking
mypy src/

# Run tests
pytest

# Check coverage
pytest --cov=src --cov-report=term-missing
```

### 4. Commit Your Changes

```bash
git add .
git commit -m "feat: add amazing new feature"
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Coding Standards

### Python Style Guide

We follow [PEP 8](https://pep8.org/) with the following specifications:

**Line Length:**
- Maximum 100 characters per line
- Use implicit line continuation inside parentheses

**Imports:**
```python
# Standard library imports first
import asyncio
import json
from typing import Any, Optional

# Third-party imports
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Local application imports
from src.models.email import Email
from src.services.ai_service import AIService
```

**Naming Conventions:**
- `snake_case` for functions, variables, and module names
- `PascalCase` for class names
- `UPPER_SNAKE_CASE` for constants
- Private methods prefix with single underscore: `_internal_method`

**Type Hints:**

Always use type hints for function signatures:

```python
# Good
async def process_email(
    email_id: str,
    session: AsyncSession,
    force_reprocess: bool = False
) -> dict[str, Any]:
    """Process an email through the AI pipeline."""
    pass

# Bad
async def process_email(email_id, session, force_reprocess=False):
    pass
```

**Docstrings:**

Use Google-style docstrings:

```python
def calculate_confidence(
    classification: str,
    probabilities: dict[str, float]
) -> float:
    """Calculate confidence score for email classification.

    Args:
        classification: The predicted category (needs_reply, spam, informational)
        probabilities: Dictionary mapping categories to probability scores

    Returns:
        Confidence score between 0.0 and 1.0

    Raises:
        ValueError: If classification not found in probabilities

    Example:
        >>> calculate_confidence('needs_reply', {'needs_reply': 0.95, 'spam': 0.05})
        0.95
    """
    if classification not in probabilities:
        raise ValueError(f"Classification '{classification}' not in probabilities")
    return probabilities[classification]
```

### Code Organization

**Services Layer:**
- Business logic goes in `src/services/`
- Each service should have a single responsibility
- Use dependency injection for database sessions and external clients

**Models Layer:**
- SQLAlchemy models in `src/models/`
- Include type hints on all columns
- Add helpful `__repr__` methods

**Schemas Layer:**
- Pydantic models in `src/schemas/`
- Use `ConfigDict` for ORM mode
- Validate external API responses with schemas

**Error Handling:**

Use custom exceptions with proper inheritance:

```python
class EmailProcessingError(Exception):
    """Base exception for email processing errors."""
    pass

class GmailAPIError(EmailProcessingError):
    """Raised when Gmail API request fails."""
    pass

class LLMRateLimitError(EmailProcessingError):
    """Raised when LLM API rate limit is hit."""
    pass
```

### Async/Await Conventions

- Always use `async def` for I/O-bound operations
- Use `await` for database queries, API calls, file operations
- Prefer `asyncio.gather()` for parallel operations:

```python
# Good - parallel execution
results = await asyncio.gather(
    fetch_email_metadata(email_id),
    fetch_email_body(email_id),
    fetch_email_attachments(email_id)
)

# Bad - sequential execution
metadata = await fetch_email_metadata(email_id)
body = await fetch_email_body(email_id)
attachments = await fetch_email_attachments(email_id)
```

### Database Best Practices

**Query Optimization:**
```python
# Good - use select with options
from sqlalchemy import select
from sqlalchemy.orm import selectinload

stmt = (
    select(Email)
    .options(selectinload(Email.responses))
    .where(Email.id == email_id)
)
result = await session.execute(stmt)
email = result.scalar_one_or_none()

# Bad - lazy loading (N+1 queries)
email = await session.get(Email, email_id)
responses = email.responses  # Triggers separate query
```

**Transactions:**
```python
# Good - explicit transaction control
async with session.begin():
    email = Email(...)
    session.add(email)
    task = ProcessingTask(email_id=email.id)
    session.add(task)
    # Commits automatically if no exception

# Bad - relying on autocommit
session.add(email)
await session.commit()
session.add(task)
await session.commit()  # Two separate transactions
```

### Logging Standards

Use structured logging with context:

```python
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Good
logger.info(
    "Email classification completed",
    email_id=email_id,
    category=result.category,
    confidence=result.confidence,
    duration_ms=duration
)

# Bad
logger.info(f"Classified email {email_id} as {result.category}")
```

### Configuration Management

- Never hardcode secrets or configuration
- Use `src/config.py` for all settings
- Validate environment variables at startup:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    DATABASE_URL: str
    REDIS_URL: str
    
    @validator('OPENAI_API_KEY')
    def validate_openai_key(cls, v):
        if not v.startswith('sk-'):
            raise ValueError('Invalid OpenAI API key format')
        return v
```

## Testing Requirements

### Test Coverage

- **Minimum coverage:** 80% overall
- **Critical paths:** 95% coverage required
  - Authentication flows
  - Email processing pipeline
  - Database operations
  - External API integrations

### Test Structure

```
tests/
├── unit/                    # Isolated component tests
│   ├── test_ai_service.py
│   ├── test_email_service.py
│   └── test_sanitizer.py
├── integration/             # Multi-component tests
│   ├── test_pipeline.py
│   └── test_api_endpoints.py
├── fixtures/                # Shared test data
│   ├── sample_emails.py
│   └── mock_responses.py
└── conftest.py             # Pytest configuration
```

### Writing Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_email_classification_success(sample_email, mock_openai_response):
    """Test successful email classification with OpenAI."""
    # Arrange
    ai_service = AIService()
    
    with patch('openai.ChatCompletion.acreate', 
               return_value=mock_openai_response):
        # Act
        result = await ai_service.classify_email(sample_email)
        
        # Assert
        assert result.category == 'needs_reply'
        assert result.confidence > 0.8
        assert 'analysis' in result.metadata

@pytest.mark.asyncio
async def test_email_classification_rate_limit():
    """Test classification handles rate limit gracefully."""
    # Arrange
    ai_service = AIService()
    
    with patch('openai.ChatCompletion.acreate', 
               side_effect=RateLimitError('Rate limit exceeded')):
        # Act & Assert
        with pytest.raises(LLMRateLimitError):
            await ai_service.classify_email(sample_email)
```

### Writing Integration Tests

```python
@pytest.mark.integration
async def test_full_email_pipeline(test_client, db_session, sample_webhook):
    """Test complete pipeline from webhook to draft creation."""
    # Trigger webhook
    response = await test_client.post(
        "/api/webhook/gmail",
        json=sample_webhook
    )
    assert response.status_code == 204
    
    # Wait for async processing
    await asyncio.sleep(5)
    
    # Verify database state
    email = await db_session.get(Email, sample_webhook['email_id'])
    assert email is not None
    assert email.processed is True
    
    # Verify task completion
    task = await db_session.get(ProcessingTask, email.task_id)
    assert task.status == 'completed'
    assert task.stage == 'draft_created'
```

### Test Fixtures

Create reusable fixtures in `conftest.py`:

```python
@pytest.fixture
async def db_session():
    """Provide test database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
    
    await engine.dispose()

@pytest.fixture
def sample_email():
    """Provide sample email data."""
    return {
        'id': 'test-email-123',
        'subject': 'Project Update Request',
        'sender': 'colleague@company.com',
        'body': 'Hi, could you provide an update on the Q2 project?'
    }
```

### Mocking External APIs

```python
@pytest.fixture
def mock_gmail_service():
    """Mock Gmail API service."""
    mock = AsyncMock()
    mock.users().messages().get.return_value.execute.return_value = {
        'id': 'test-123',
        'payload': {
            'headers': [
                {'name': 'Subject', 'value': 'Test Subject'},
                {'name': 'From', 'value': 'test@example.com'}
            ],
            'body': {'data': base64.b64encode(b'Test body').decode()}
        }
    }
    return mock
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_ai_service.py

# Run with markers
pytest -m "not integration"  # Skip integration tests
pytest -m integration         # Only integration tests

# Run with verbose output
pytest -v

# Run and stop at first failure
pytest -x
```

## Commit Message Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only changes
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding or updating tests
- `chore`: Changes to build process or auxiliary tools
- `ci`: Changes to CI configuration

### Scopes

- `api`: FastAPI endpoints
- `worker`: Celery tasks
- `database`: Database models or migrations
- `ai`: AI/LLM integration
- `gmail`: Gmail API integration
- `monitoring`: Prometheus/Grafana/Loki
- `config`: Configuration changes
- `deps`: Dependency updates

### Examples

```bash
# Feature
git commit -m "feat(ai): add Claude fallback for OpenAI failures"

# Bug fix
git commit -m "fix(worker): prevent duplicate email processing
  
Add deduplication check in classify_email task to handle
race conditions when webhook fires multiple times for same email."

# Documentation
git commit -m "docs(readme): add troubleshooting section for OAuth errors"

# Breaking change
git commit -m "feat(api)!: change webhook response format

BREAKING CHANGE: Webhook now returns JSON response instead of 204.
Update Pub/Sub subscription to handle new format."
```

### Subject Line Rules

- Use imperative mood ("add", not "added" or "adds")
- Don't capitalize first letter
- No period at the end
- Maximum 72 characters
- Be specific and descriptive

## Pull Request Process

### Before Submitting PR

**Checklist:**

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (README, docstrings, etc.)
- [ ] Tests added or updated
- [ ] All tests pass locally
- [ ] No merge conflicts with main branch
- [ ] Commit messages follow guidelines

### PR Title Format

Use same format as commit messages:

```
feat(worker): add retry mechanism for transient Gmail API errors
```

### PR Description Template

```markdown
## Description
Brief description of changes

## Motivation and Context
Why is this change required? What problem does it solve?

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## How Has This Been Tested?
Describe the tests you ran to verify your changes

## Screenshots (if applicable)

## Checklist
- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published
```

### Review Process

1. **Automated Checks**: CI pipeline must pass
   - Linting (Ruff)
   - Type checking (mypy)
   - Tests (pytest)
   - Coverage threshold (80%)

2. **Code Review**: At least one approval required
   - Reviewers will provide constructive feedback
   - Address all comments or provide reasoning
   - Push additional commits to address feedback

3. **Final Review**: Maintainer approval
   - Ensures alignment with project goals
   - Verifies documentation completeness
   - Checks for security concerns

4. **Merge**: Squash and merge strategy
   - All commits squashed into single commit
   - Clean git history maintained

### After PR Merge

- Delete your feature branch
- Pull latest main branch
- Close related issues if applicable

## Issue Reporting

### Bug Reports

Use the bug report template:

```markdown
**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Set up environment with '...'
2. Send email to '...'
3. Observe error '...'

**Expected behavior**
A clear and concise description of what you expected to happen.

**Actual behavior**
What actually happened

**Logs**
```
Paste relevant logs here
```

**Environment:**
- OS: [e.g. Ubuntu 22.04]
- Python version: [e.g. 3.11.4]
- Docker version: [e.g. 24.0.5]
- Relevant package versions

**Additional context**
Add any other context about the problem here.
```

### Feature Requests

```markdown
**Is your feature request related to a problem?**
A clear and concise description of what the problem is.

**Describe the solution you'd like**
A clear and concise description of what you want to happen.

**Describe alternatives you've considered**
A clear and concise description of any alternative solutions or features you've considered.

**Additional context**
Add any other context or screenshots about the feature request here.

**Would you like to implement this feature?**
- [ ] Yes, I'd like to work on this
- [ ] No, but I'm available for testing
- [ ] No, just suggesting
```

## Development Environment Setup

### Local Development (No Docker)

For rapid development without Docker:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements-dev.txt

# Start PostgreSQL locally
createdb email_assistant

# Start Redis locally
redis-server

# Run migrations
alembic upgrade head

# Start FastAPI
uvicorn src.main:app --reload

# Start Celery worker in separate terminal
celery -A src.workers.celery_app worker --loglevel=info

# Start Celery beat in separate terminal
celery -A src.workers.celery_app beat --loglevel=info
```

### IDE Configuration

**VS Code** (`.vscode/settings.json`):

```json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
```

**PyCharm**:
- Enable Ruff as external tool
- Configure pytest as default test runner
- Enable type checking in inspections

## Architecture Guidelines

### Adding New Services

When adding a new service module:

1. Create service file in `src/services/`
2. Define service class with clear responsibilities
3. Use dependency injection for external dependencies
4. Add comprehensive docstrings
5. Write unit tests with mocks
6. Update architecture documentation

Example service structure:

```python
from src.utils.logging import get_logger

logger = get_logger(__name__)

class NewService:
    """Service for handling X functionality.
    
    This service is responsible for:
    - Task 1
    - Task 2
    - Task 3
    """
    
    def __init__(
        self,
        db_session: AsyncSession,
        external_client: ExternalAPI
    ):
        self.db = db_session
        self.client = external_client
    
    async def main_operation(self, input_data: dict) -> dict:
        """Perform main operation.
        
        Args:
            input_data: Input parameters
            
        Returns:
            Operation results
            
        Raises:
            ServiceError: If operation fails
        """
        logger.info("Starting operation", input_keys=list(input_data.keys()))
        
        try:
            result = await self._internal_logic(input_data)
            logger.info("Operation completed", result_size=len(result))
            return result
        except Exception as e:
            logger.error("Operation failed", error=str(e))
            raise ServiceError(f"Operation failed: {e}") from e
    
    async def _internal_logic(self, data: dict) -> dict:
        """Internal helper method."""
        pass
```

### Adding New Database Models

1. Create model in `src/models/`
2. Add Alembic migration
3. Create corresponding Pydantic schema
4. Update repository layer if needed
5. Add tests for CRUD operations

Example model:

```python
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

class NewEntity(Base):
    """Database model for new entity."""
    
    __tablename__ = "new_entities"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    
    def __repr__(self) -> str:
        return f"<NewEntity(id={self.id}, name='{self.name}')>"
```

### Adding New Celery Tasks

1. Define task in `src/workers/tasks.py`
2. Configure retry behavior
3. Add metrics tracking
4. Include correlation ID for tracing
5. Add integration tests

Example task:

```python
@celery_app.task(
    bind=True,
    autoretry_for=(TransientError,),
    retry_backoff=60,
    retry_backoff_max=900,
    max_retries=5,
)
def new_async_task(
    self: Task,
    entity_id: str,
    correlation_id: str | None = None
) -> dict[str, Any]:
    """Process entity asynchronously.
    
    Args:
        entity_id: Entity identifier
        correlation_id: Request correlation ID for tracing
        
    Returns:
        Task execution result
        
    Raises:
        TransientError: For retriable failures
        PermanentError: For non-retriable failures
    """
    bind_correlation_id(correlation_id or str(uuid.uuid4()))
    logger.info("Task started", entity_id=entity_id)
    
    try:
        service = NewService()
        result = asyncio.run(service.process(entity_id))
        
        logger.info("Task completed", entity_id=entity_id)
        return {"status": "success", "result": result}
        
    except TransientError as e:
        logger.warning("Transient error, will retry", error=str(e))
        raise  # Celery will retry
        
    except PermanentError as e:
        logger.error("Permanent error, no retry", error=str(e))
        raise  # Goes to dead-letter queue
```

## Documentation Standards

### Code Documentation

- Every module should have a module-level docstring
- Every public function/method should have a docstring
- Every class should have a class-level docstring
- Complex algorithms should have inline comments

### API Documentation

- Use FastAPI's automatic OpenAPI generation
- Add detailed descriptions to route decorators
- Provide request/response examples
- Document all possible error codes

```python
@router.post(
    "/process-email",
    response_model=TaskResponse,
    status_code=201,
    summary="Trigger email processing",
    description="""
    Manually trigger email processing for a specific email ID.
    
    This endpoint bypasses the webhook and directly creates a processing task.
    Useful for:
    - Reprocessing failed emails
    - Manual intervention scenarios
    - Testing and debugging
    """,
    responses={
        201: {
            "description": "Task created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "task_id": "abc-123",
                        "email_id": "18f3a2b1c5d4e6f7",
                        "status": "pending"
                    }
                }
            }
        },
        400: {"description": "Invalid email ID format"},
        404: {"description": "Email not found"},
        429: {"description": "Rate limit exceeded"}
    }
)
async def process_email(request: ProcessEmailRequest):
    pass
```

### Architecture Documentation

When making architectural changes:

1. Update `ARCHITECTURE.md`
2. Create ADR (Architecture Decision Record) in `docs/adr/`
3. Update sequence diagrams if workflow changes
4. Update README architecture section

## Questions?

If you have questions about contributing:

- Check existing [GitHub Issues](https://github.com/[USERNAME]/ai-email-assistant/issues)
- Start a [GitHub Discussion](https://github.com/[USERNAME]/ai-email-assistant/discussions)
- Reach out to maintainers

---

**Thank you for contributing to AI Email Assistant!** 🎉
