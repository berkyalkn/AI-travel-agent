# server/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from agent import app as travel_agent_app


origins = [
    "http://localhost:5173", 
    "http://localhost:3000", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)


app = FastAPI(
    title="AI Travel Agent API",
    description="An API to generate travel itineraries using a multi-agent system."
)

class PlanRequest(BaseModel):
    user_query: str

@app.get("/")
def read_root():
    return {"status": "AI Travel Agent API is running."}

@app.post("/plan-trip")
async def plan_trip(request: PlanRequest):
    """
    Takes a user query and returns a generated travel plan.
    """
    try:
        print(f"Received request for query: {request.user_query}")
        initial_state = {"user_request": request.user_query}

        final_state = travel_agent_app.invoke(initial_state)

        report = final_state.get("markdown_report", "No report was generated.")

        return {"report": report}

    except Exception as e:
        print(f"An error occurred: {e}")
        return {"error": str(e)}