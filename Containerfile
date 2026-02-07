FROM python:3.12-slim

WORKDIR /app/

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml README.md ./

# Install dependencies (without dev dependencies)
# Using --no-dev to exclude optional dev dependencies
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy configuration and schema files
COPY asu.yaml asu_schema.json ./

# Copy application code
COPY ./asu/ ./asu/

# Run the application
CMD uv run uvicorn --host 0.0.0.0 'asu.main:app'
