from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from agent import app as travel_agent_app


app = FastAPI(
    title="AI Travel Agent API",
    description="An API to generate travel itineraries using a multi-agent system."
)


origin = "http://localhost:5173", 
     
app.add_middleware(
    CORSMiddleware,
    allow_origins=origin,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

class PlanRequest(BaseModel):
    user_query: str

@app.get("/")
def read_root():
    return {"status": "AI Travel Agent API is running."}

@app.post("/plan-trip")
async def plan_trip(request: PlanRequest):
    try:
        print(f"Received request for query: {request.user_query}")
        initial_state = {"user_request": request.user_query}
        final_state = travel_agent_app.invoke(initial_state)
        
        final_report_markdown = final_state.get("markdown_report")
        
        if final_report_markdown:
            return {"report": final_report_markdown}
        else:
            return {"error": "Failed to generate the final report markdown."}

    except Exception as e:
        print(f"AN ERROR OCCURRED: {e}")        
        error_str = str(e).lower()
        
        if "tool call validation failed" in error_str or "400" in error_str:
            user_friendly_error = "I couldn't understand the details of your request. Please ensure all fields are filled clearly (especially dates) and try again."
            return {"error": user_friendly_error}
        
        if "service unavailable" in error_str or "503" in error_str:
            user_friendly_error = "The AI service is currently experiencing high traffic. Please try again in a moment."
            return {"error": user_friendly_error}

        return {"error": "An unexpected error occurred while planning your trip. Please try again later."}