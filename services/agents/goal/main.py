"""
GoalAgent — container entry point.

Environment variables (required at runtime):
    AGENT_ID              goal_agent
    AGENT_ENDPOINT        http://goal_agent:8005
    REGISTRY_URL          http://api:8000
    AGENT_CAPABILITIES    goal,planning,savings
"""

from services.agents._common.fastapi_app import make_agent_app
from services.agents.goal.agent import GoalAgent

app = make_agent_app(GoalAgent)
