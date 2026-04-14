"""
RiskAgent — container entry point.

Environment variables (required at runtime):
    AGENT_ID              risk_agent
    AGENT_ENDPOINT        http://risk_agent:8004
    REGISTRY_URL          http://api:8000
    AGENT_CAPABILITIES    risk,insurance,emergency_fund,debt
"""

from services.agents._common.fastapi_app import make_agent_app
from services.agents.risk.agent import RiskAgent

app = make_agent_app(RiskAgent)
