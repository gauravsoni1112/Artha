"""
CashflowAgent — container entry point.

Builds a FastAPI app using the shared factory and serves it via uvicorn.

Environment variables (required at runtime):
    AGENT_ID              cashflow_agent
    AGENT_ENDPOINT        http://cashflow_agent:8001
    REGISTRY_URL          http://api:8000
    AGENT_CAPABILITIES    cashflow,spending,budget

    DATABASE_URL          postgresql+asyncpg://...
    LLM_PROVIDER          ollama   (or anthropic / openai)
    LLM_MODEL             llama3.2
    LLM_BASE_URL          http://ollama:11434

    CASHFLOW_AGENT_LLM_*  optional per-agent overrides
"""

from services.agents._common.fastapi_app import make_agent_app
from services.agents.cashflow.agent import CashflowAgent

app = make_agent_app(CashflowAgent)
