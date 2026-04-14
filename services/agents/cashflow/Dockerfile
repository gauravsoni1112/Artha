FROM python:3.12-slim

WORKDIR /app

# Install only what's needed for the agent container
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[agents]" 2>/dev/null || pip install --no-cache-dir -e "."

COPY libs/ ./libs/
COPY services/agent/ ./services/agent/
COPY services/agents/_common/ ./services/agents/_common/
COPY services/agents/cashflow/ ./services/agents/cashflow/

ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=cashflow_agent
ENV AGENT_CAPABILITIES=cashflow,spending,budget

EXPOSE 8001

CMD ["uvicorn", "services.agents.cashflow.main:app", "--host", "0.0.0.0", "--port", "8001"]
