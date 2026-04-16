FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[agents]" 2>/dev/null || pip install --no-cache-dir -e "."

COPY libs/ ./libs/
COPY services/agent/ ./services/agent/
COPY services/agents/_common/ ./services/agents/_common/
COPY services/agents/goal/ ./services/agents/goal/

ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=goal_agent
ENV AGENT_CAPABILITIES=goal,planning,savings

EXPOSE 8005

CMD ["uvicorn", "services.agents.goal.main:app", "--host", "0.0.0.0", "--port", "8005"]
