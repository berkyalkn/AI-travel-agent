import os
from fastapi import FastAPI, HTTPException
from langchain_tavily import TavilySearch
from schemas import ActivitySearchRequest
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

Instrumentator().instrument(app).expose(app)

@app.post("/search_activities", response_model=str)
def search_activities(request: ActivitySearchRequest):
    print(f"--- Processing Activity Search for {request.destination} ---")
    
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY not found in environment")

    all_results_summary = ""
    tavily_search = TavilySearch(max_results=4, api_key=tavily_api_key)
    
    for interest in request.interests:
        query = f"specific and famous '{interest}' places, landmarks, or experiences in {request.destination}. Give me names of places, not tours."
        print(f"-> Searching Tavily for: {interest}")
        
        try:
            response_data = tavily_search.invoke(query)
            
            search_results = []
            if isinstance(response_data, dict):
                search_results = response_data.get('results', [])
            elif isinstance(response_data, list):
                search_results = response_data
            
            all_results_summary += f"\n--- Search Results for '{interest}' in {request.destination} ---\n"

            if not search_results:
                all_results_summary += "No specific results found for this interest.\n\n"
                continue

            for result in search_results:
                if isinstance(result, dict):
                    title = result.get('title', 'N/A')
                    content = result.get('content', 'No content')
                    all_results_summary += f"Title: {title}\nContent: {content}\n\n"
        
        except Exception as e:
            print(f"Tavily Error for '{interest}': {e}")
            continue

    if not all_results_summary.strip():
        return "No relevant activities found from web search."
         
    return all_results_summary