FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[agents]" 2>/dev/null || pip install --no-cache-dir -e "."

COPY libs/ ./libs/
COPY services/agent/ ./services/agent/
COPY services/agents/_common/ ./services/agents/_common/
COPY services/agents/risk/ ./services/agents/risk/

ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=risk_agent
ENV AGENT_CAPABILITIES=risk,insurance,emergency_fund,debt

EXPOSE 8004

CMD ["uvicorn", "services.agents.risk.main:app", "--host", "0.0.0.0", "--port", "8004"]
