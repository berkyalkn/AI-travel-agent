import json
import asyncio
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse


from agent import app as travel_agent_app


app = FastAPI(
    title="AI Travel Agent API",
    description="An API to generate travel itineraries using a multi-agent system."
)


origins = [
    "http://localhost:5173", 
    "http://localhost:3000", 
    "http://127.0.0.1:3000",
    "http://travel-frontend-route-travel-agent-project.apps-crc.testing"
]
     
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PlanRequest(BaseModel):
    user_query: str

@app.get("/")
def read_root():
    return {"status": "AI Travel Agent API is running."}


@app.post("/plan-trip-stream")
async def plan_trip_stream(request: PlanRequest):
    initial_state = {"user_request": request.user_query}

    async def event_stream():
        try:
           
            async for chunk in travel_agent_app.astream(initial_state):
                for key, value in chunk.items():
                    node_name = key
                    node_output = value
                    
                    status_message = f"Working on: {node_name.replace('_', ' ').title()}"
                    print(f"Streaming status: {status_message}")

                    yield f"event: status\ndata: {json.dumps({'message': status_message})}\n\n"
                    await asyncio.sleep(0.1) 

            final_state = node_output 
            final_report_markdown = final_state.get("markdown_report")
            map_html_content = final_state.get("map_html")

            final_data = {
                "markdown_report": final_report_markdown,
                "map_html": map_html_content
            }
            yield f"event: final_report\ndata: {json.dumps(final_data)}\n\n"

        except Exception as e:
            print(f"AN ERROR OCCURRED during stream: {e}")
            error_message = f"An error occurred: {e}"
            yield f"event: error\ndata: {json.dumps({'message': error_message})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

"""
@app.post("/plan-trip")
async def plan_trip(request: PlanRequest):
    try:
        print(f"Received request for query: {request.user_query}")
        initial_state = {"user_request": request.user_query}
        final_state = travel_agent_app.invoke(initial_state)
        
        final_report_markdown = final_state.get("markdown_report")
        map_html_content = final_state.get("map_html")

        if final_report_markdown:
            return {
                "markdown_report": final_report_markdown,
                "map_html": map_html_content
            }
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
"""
