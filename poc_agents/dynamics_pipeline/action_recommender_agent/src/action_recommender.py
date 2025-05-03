"""
Entrypoint module for the Action Recommendation Agent.
This file serves as the direct entrypoint for Uvicorn to avoid Python import issues.
"""

from action_recommender_agent.main import app

# This allows uvicorn to import just the module directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8054)
