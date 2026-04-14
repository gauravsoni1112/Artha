"""
TaxAgent — container entry point.

Environment variables (required at runtime):
    AGENT_ID              tax_agent
    AGENT_ENDPOINT        http://tax_agent:8003
    REGISTRY_URL          http://api:8000
    AGENT_CAPABILITIES    tax,itr,fiscal
"""

from services.agents._common.fastapi_app import make_agent_app
from services.agents.tax.agent import TaxAgent

app = make_agent_app(TaxAgent)
