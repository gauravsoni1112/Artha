"""
InvestmentAgent — container entry point.

Environment variables (required at runtime):
    AGENT_ID              investment_agent
    AGENT_ENDPOINT        http://investment_agent:8002
    REGISTRY_URL          http://api:8000
    AGENT_CAPABILITIES    investment,portfolio,net_worth
"""

from services.agents._common.fastapi_app import make_agent_app
from services.agents.investment.agent import InvestmentAgent

app = make_agent_app(InvestmentAgent)
