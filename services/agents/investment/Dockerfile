FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[agents]" 2>/dev/null || pip install --no-cache-dir -e "."

COPY libs/ ./libs/
COPY services/agent/ ./services/agent/
COPY services/agents/_common/ ./services/agents/_common/
COPY services/agents/investment/ ./services/agents/investment/

ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=investment_agent
ENV AGENT_CAPABILITIES=investment,portfolio,net_worth

EXPOSE 8002

CMD ["uvicorn", "services.agents.investment.main:app", "--host", "0.0.0.0", "--port", "8002"]
