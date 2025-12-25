import os
import requests
import json
import markdown2
import folium
from folium import plugins
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from state import TripState
from dotenv import load_dotenv
from datetime import datetime, timedelta 
from schemas import * 

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")

if not all([groq_api_key, gemini_api_key]):
    raise ValueError("GROQ_API_KEY or GEMINI_API_KEY is missing from .env file!")

llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    api_key=groq_api_key, 
    max_retries=3
)

llm_gemini = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", 
    temperature=0.1,
    google_api_key=gemini_api_key
)


def planner_agent(state: TripState) -> dict:
    """
    Takes the user request and converts it into a structured TripRequest object
    using the robust .bind_tools() method.
    """
    print("--- Running Planner Agent ---")
    
    planner_llm = llm.bind_tools([TripRequest])
    
    prompt = f"""
    You are an expert at parsing user travel requests.
    Parse the following user request into a structured TripRequest object.
    Extract the origin, destination, start date, end date, number of people, budget, and key interests.
    Today's date is {datetime.now().strftime('%Y-%m-%d')}. Dates must be in YYYY-MM-DD format.

    User Request: "{state['user_request']}"
    """
    
    ai_message = planner_llm.invoke(prompt)
    
    if not ai_message.tool_calls:
        raise ValueError("Planner agent failed to parse the user request into a structured plan.")
        
    tool_call = ai_message.tool_calls[0]
    plan = TripRequest(**tool_call['args'])
    
    print(f"-> Structured Plan: {plan.model_dump_json(indent=2)}")
    
    return {"trip_plan": plan, "refinement_count": 0}



def flight_agent(state: TripState) -> dict:
    """
    Orchestrates the flight search by calling the dedicated Flight Microservice.
    """
    print("--- Running Flight Agent (Microservice Proxy) ---")
    trip_plan = state['trip_plan']
    if not trip_plan: return {}

    payload = {
        "origin": trip_plan.origin,
        "destination": trip_plan.destination,
        "start_date": trip_plan.start_date,
        "end_date": trip_plan.end_date,
        "person": trip_plan.person
    }

    service_url = "http://flight-service:8000/search"
    
    flight_options = []
    
    try:
        print(f"-> Sending request to Flight Service: {service_url}")
        response = requests.post(service_url, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        flight_options = [FlightInfo(**item) for item in data]
        print(f"-> Received {len(flight_options)} flight options from service.")
        
    except requests.exceptions.RequestException as e:
        print(f"-> ERROR calling Flight Service: {e}")
        return {"flight_options": [], "selected_flight": None}

    if not flight_options:
        print("-> No flights found via service.")
        return {"flight_options": [], "selected_flight": None}

    print("-> Step 3: LLM making intelligent selection...")
    selection_llm = llm.bind_tools([FlightSelection])

    options_text = ""
    for i, opt in enumerate(flight_options):
        options_text += f"Option {i}: Airline: {opt.departure_leg.airline}, Price: €{opt.price:.2f}, Duration: {opt.total_duration_minutes}m\n"

    prompt = f"""
    You are an expert flight travel agent. Select the BEST flight option.
    CRITERIA:
    1. Budget: {state['trip_plan'].budget}.
    2. Convenience: Short duration is better.
    
    Options:
    {options_text}
    """

    ai_message = selection_llm.invoke(prompt)
    selected_flight = None

    if ai_message.tool_calls:
        tool_call = ai_message.tool_calls[0]
        selection = FlightSelection(**tool_call['args'])
        if selection.best_option_index < len(flight_options):
            selected_flight = flight_options[selection.best_option_index]
            print(f"-> LLM selected: {selected_flight.departure_leg.airline}")
    else:
         selected_flight = flight_options[0] 

    return {"flight_options": flight_options, "selected_flight": selected_flight}


def hotel_agent(state: TripState) -> dict:
    """
    Orchestrates the hotel search via Hotel Microservice.
    Includes refinement check to avoid re-calling API if options exist.
    """
    print("--- Running Hotel Agent (Microservice Proxy) ---")
    trip_plan = state['trip_plan']
    if not trip_plan: return {}

    hotel_options = []

    if state.get("hotel_options") and len(state.get("hotel_options", [])) > 1:
        print("-> Refinement loop detected. Using existing hotel list (No API Call).")
        hotel_options = state["hotel_options"]
    
    else:
        payload = {
            "destination": trip_plan.destination,
            "start_date": trip_plan.start_date,
            "end_date": trip_plan.end_date,
            "person": trip_plan.person
        }
        service_url = "http://hotel-service:8001/search"
        
        try:
            print(f"-> Sending request to Hotel Service: {service_url}")
            response = requests.post(service_url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            hotel_options = [HotelInfo(**item) for item in data]
            print(f"-> Received {len(hotel_options)} hotel options.")
        except Exception as e:
            print(f"-> ERROR calling Hotel Service: {e}")
            return {"hotel_options": [], "selected_hotel": None}

    if not hotel_options:
        return {"hotel_options": [], "selected_hotel": None}

    print("-> Step 3: LLM making a smart selection...")
    selection_llm = llm.bind_tools([HotelSelection])

    options_text = ""
    for i, opt in enumerate(hotel_options):
        options_text += f"Option {i}: Name: {opt.hotel_name}, Rating: {opt.rating}/10, Total Price: €{opt.total_price:.2f}\n"

    refinement_feedback = ""
    if state.get("refinement_count", 0) > 0 and state.get("evaluation_result"):
        refinement_feedback = f"The previous attempt exceeded the budget. Feedback: '{state['evaluation_result'].feedback}'. Please focus on finding a more budget-friendly yet still good option this time."

    prompt = f"""
    You are an expert travel advisor. Your task is to select the best hotel for the user from the list below.
    {refinement_feedback}
    The user cares about their budget. Find the best balance between a high rating and a price that reasonably fits the user's budget.

    USER PREFERENCES:
    - Budget: €{trip_plan.budget}

    HOTEL OPTIONS:
    {options_text}

    Analyze the options based on both rating and price. Select the hotel that offers the best value for money.
    """

    ai_message = selection_llm.invoke(prompt)
    selected_hotel = None

    if ai_message.tool_calls:
        tool_call = ai_message.tool_calls[0]
        selection = HotelSelection(**tool_call['args'])
        
        if selection.best_option_index < len(hotel_options):
            selected_hotel = hotel_options[selection.best_option_index]
            print(f"-> LLM reasoning: {selection.reasoning}")
            print(f"-> LLM selected hotel: {selected_hotel.hotel_name}")
        else:
            print("-> WARNING: Invalid index from LLM. Defaulting to first option.")
            selected_hotel = hotel_options[0]
    else:
        print("-> WARNING: LLM didn't call tool. Defaulting to first option.")
        selected_hotel = hotel_options[0]

    return {"hotel_options": hotel_options, "selected_hotel": selected_hotel}



def event_agent(state: TripState) -> dict:
    """Finds events via Microservice and then uses an LLM to select the list based on user interests."""
    print("--- Running Smart Event Agent (Microservice Proxy) ---")

    trip_plan = state['trip_plan']
    if not trip_plan or not trip_plan.interests: return {"events": []}
    
    payload = {
        "city": trip_plan.destination,
        "start_date": trip_plan.start_date,
        "end_date": trip_plan.end_date
    }
    
    service_url = "http://event-service:8004/search_events"
    
    all_events = []
    try:
        print(f"-> Sending request to Event Service: {service_url}")
        response = requests.post(service_url, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        all_events = [EventInfo(**item) for item in data]
        print(f"-> Received {len(all_events)} events from service.")
        
    except Exception as e:
        print(f"-> ERROR calling Event Service: {e}")
        return {"events": []}
    
    if not all_events:
        return {"events": []}
    
    selected_llm = llm.bind_tools([SelectedEvents])
    
    events_json = json.dumps([event.model_dump() for event in all_events])

    prompt = f"""
    You are an expert event curator. Based on a user's interests, your task is to select the most relevant events from a provided list.

    User's Interests: {', '.join(trip_plan.interests)}

    Here is a list of events happening during their trip. Please review them, remove any duplicates or near-duplicates (like the same museum entry listed multiple times), and select the top 3-4 most relevant events that best match the user's interests.

    LIST OF AVAILABLE EVENTS:
    {events_json}

    Now, call the `SelectedEvents` function with your final, selected list of events.
    """
    
    ai_message = selected_llm.invoke(prompt)
    
    if not ai_message.tool_calls:
        print("-> LLM failed to select events. Returning top 5.")
        return {"events": all_events[:5]} 
        
    tool_call = ai_message.tool_calls[0]
    selected_list = SelectedEvents(**tool_call['args'])
    
    print(f"-> LLM select the list down to {len(selected_list.events)} relevant events.")
    
    return {"events": selected_list.events}



def data_aggregator_agent(state: TripState) -> dict:
    """A simple node to act as a synchronization point for parallel branches."""
    print("--- Aggregating Flight, Hotel, and Event data ---")
   
    return {}



def activity_extraction_agent(state: TripState) -> dict:
    """
    Analyzes the raw text from Tavily (via Activity Microservice) and extracts a structured list of activities.
    """
    print("--- Running Activity Extraction Agent (Microservice Proxy) ---")
    trip_plan = state['trip_plan']
    
    payload = {
        "destination": trip_plan.destination,
        "interests": trip_plan.interests
    }
    
    service_url = "http://activity-service:8002/search_activities"
    
    raw_activity_data = ""
    
    try:
        print(f"-> Sending request to Activity Service: {service_url}")
        response = requests.post(service_url, json=payload, timeout=60)
        response.raise_for_status()
        
        raw_activity_data = response.json()
        
    except Exception as e:
        print(f"-> ERROR calling Activity Service: {e}")
        return {"extracted_activities": []}

    if not raw_activity_data or "No relevant activities found" in raw_activity_data:
        print("-> No usable text from web search.")
        return {"extracted_activities": []}

    extraction_llm = llm.bind_tools([ExtractedActivities])
    
    prompt = f"""
    You are a data extraction expert. Your task is to analyze the provided text from a web search
    and extract all specific, physical, and geocodable places.

    **CRITICAL INSTRUCTIONS:**
    -   You MUST extract **only real, physical locations** like museums, monuments, parks, squares, famous buildings, or specific neighborhoods.
    -   You MUST **AVOID** extracting temporary items like event names, exhibitions, festivals, awards, or abstract concepts (e.g., "art-house cinema under the stars").
    -   For each extracted place, provide a `name`, `description`, `location` (city name: "{trip_plan.destination}"), and a suitable `time_of_day`.

    **Example of what to do:**
    -   Good Extraction (Physical Place): "Colosseum", "Vatican Museums", "Trastevere Neighborhood"
    -   Bad Extraction (Event/Concept): "International Organ Festival", "From Pop to Eternity exhibition"

    **RAW SEARCH RESULTS:**
    ---
    {raw_activity_data}
    ---

    Now, call the `ExtractedActivities` function with the list of all the **physical places** you found.
    """
    
    ai_message = extraction_llm.invoke(prompt)
    
    if not ai_message.tool_calls:
        print("-> LLM failed to extract any activities.")
        return {"extracted_activities": []}
        
    tool_call = ai_message.tool_calls[0]
    extracted = ExtractedActivities(**tool_call['args'])
    
    print(f"-> Extracted {len(extracted.activities)} specific activities.")
    return {"extracted_activities": extracted.activities}


def geocoding_agent(state: TripState) -> dict:
    """
    Orchestrates geocoding by calling the dedicated Geocoding Microservice.
    """
    print("--- Running Geocoding Agent (Microservice Proxy) ---")
    activities = state.get("extracted_activities")
    if not activities:
        return {}

    service_url = "http://geocoding-service:8003/geocode"
    
    updated_activities = []
    
    for activity in activities:
        search_query = f"{activity.name}, {state['trip_plan'].destination}"
        
        payload = {"query": search_query}
        
        try:
            response = requests.post(service_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data['latitude'] and data['longitude']:
                    activity.latitude = data['latitude']
                    activity.longitude = data['longitude']
                    print(f"-> Geocoded: {activity.name}")
            else:
                print(f"-> Failed to geocode {activity.name}. Status: {response.status_code}")
                
        except Exception as e:
            print(f"-> Error geocoding {activity.name}: {e}")
        
        updated_activities.append(activity)
    
    return {"extracted_activities": updated_activities}



def activity_scheduling_agent(state: TripState) -> dict:
    """
    Schedules the activities day by day using LLM.
    Includes robust error handling for LLM tool call failures.
    And MOST IMPORTANTLY: Re-attaches coordinates to the scheduled activities.
    """
    print("--- Running Activity Scheduling Agent ---")
    
    extracted_activities = state.get("extracted_activities", [])
    events = state.get("events", [])
    trip_plan = state["trip_plan"]

    if not extracted_activities and not events:
        print("-> Missing data, cannot schedule.")
        return {"final_itinerary": None}

    print(f"-> Received {len(extracted_activities)} activities and {len(events)} events to schedule.")

    activity_lookup = {act.name: act for act in extracted_activities}

    scheduler_llm = llm.bind_tools([ScheduledActivities])
    
    activities_text = "\n".join([f"- {act.name}: {act.description} ({act.time_of_day})" for act in extracted_activities])
    events_text = "\n".join([f"- {evt.name} on {evt.date} at {evt.venue}" for evt in events])

    prompt = f"""
    You are an expert travel planner. Create a day-by-day itinerary for a {trip_plan.days}-day trip to {trip_plan.destination}.

    **Inputs:**
    - Trip Duration: {trip_plan.days} days
    - Activities to fit in:
    {activities_text}
    
    - Fixed Events (Must happen on their specific date):
    {events_text}

    **Instructions:**
    1. Distribute these activities logically across {trip_plan.days} days.
    2. Group nearby activities together to minimize travel time.
    3. Ensure each day has a balanced mix of morning, afternoon, and evening activities.
    4. Call the `ScheduledActivities` tool with your final plan.
    5. IMPORTANT: Use the EXACT activity names provided in the input list.
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            ai_message = scheduler_llm.invoke(prompt)
            
            if ai_message.tool_calls:
                tool_call = ai_message.tool_calls[0]
                scheduled_plan = ScheduledActivities(**tool_call['args'])
                
                for day_plan in scheduled_plan.daily_plans:
                    for scheduled_act in day_plan.activities:
                        original_act = activity_lookup.get(scheduled_act.name)
                        
                        if original_act and original_act.latitude and original_act.longitude:
                            scheduled_act.latitude = original_act.latitude
                            scheduled_act.longitude = original_act.longitude
                        else:
                            for orig_name, orig_act in activity_lookup.items():
                                if scheduled_act.name in orig_name or orig_name in scheduled_act.name:
                                    if orig_act.latitude and orig_act.longitude:
                                        scheduled_act.latitude = orig_act.latitude
                                        scheduled_act.longitude = orig_act.longitude
                                        break

                final_itinerary = Itinerary(
                    selected_flight=state['selected_flight'],
                    selected_hotel=state['selected_hotel'],
                    daily_plans=scheduled_plan.daily_plans
                )
                print("-> Final Itinerary Assembled Successfully (Coordinates Preserved).")
                return {"final_itinerary": final_itinerary}
            
            else:
                print(f"-> Attempt {attempt+1}: LLM did not call tool. Retrying...")

        except Exception as e:
            print(f"-> Attempt {attempt+1} Error: {e}")
            continue

    print("-> FAILED: LLM could not generate a valid schedule after retries.")
    return {"final_itinerary": None}
    


def evaluator_agent(state: TripState) -> dict:
    print("--- Running Smart Evaluator Agent (High IQ Mode) ---")
    trip_plan = state['trip_plan']
    selected_flight = state['selected_flight']
    selected_hotel = state['selected_hotel']
    flight_options = state['flight_options']
    hotel_options = state['hotel_options']
    refinement_count = state.get('refinement_count', 0)
    
    flight_and_hotel_cost = selected_flight.price + selected_hotel.total_price 
    daily_spending = trip_plan.daily_spending_budget if trip_plan.daily_spending_budget else 0
    total_daily_spending = daily_spending * trip_plan.person * trip_plan.days
    total_cost = flight_and_hotel_cost + total_daily_spending
    budget = trip_plan.budget


    next_hotel_info = "None"
    if len(hotel_options) > refinement_count + 1:
        h = hotel_options[refinement_count + 1]
        diff = selected_hotel.total_price - h.total_price
        next_hotel_info = f"""
        Name: {h.hotel_name}
        Price: €{h.total_price} (Saves €{diff:.2f})
        Rating: {h.rating} (Current is {selected_hotel.rating})
        """

    next_flight_info = "None"
    if len(flight_options) > refinement_count + 1:
        f = flight_options[refinement_count + 1]
        diff = selected_flight.price - f.price
        duration_diff = f.departure_leg.duration_minutes - selected_flight.departure_leg.duration_minutes
        duration_msg = f"{duration_diff} mins longer" if duration_diff > 0 else f"{abs(duration_diff)} mins shorter"
        
        next_flight_info = f"""
        Airline: {f.departure_leg.airline}
        Price: €{f.price} (Saves €{diff:.2f})
        Duration Change: {duration_msg}
        Stops: {'Direct' if not f.departure_leg.is_layover else 'Has Layover'}
        """

    evaluator_llm = llm_gemini.bind_tools([EvaluationResult])

    prompt = f"""
    You are an expert Travel Consultant. Your goal is to maximize the user's experience while trying to respect the budget.
    
    **Current Status:**
    - Budget: €{budget}
    - Total Cost: €{total_cost:.2f}
    - Status: {'Over Budget' if total_cost > budget else 'Within Budget'}

    **Current Selection Quality:**
    - Flight: {selected_flight.departure_leg.airline}, Duration: {selected_flight.departure_leg.duration_minutes} mins, Price: €{selected_flight.price}
    - Hotel: {selected_hotel.hotel_name}, Rating: {selected_hotel.rating}/10, Price: €{selected_hotel.total_price}

    **Alternative Options for Refinement:**
    - Option A (Cheaper Hotel): {next_hotel_info}
    - Option B (Cheaper Flight): {next_flight_info}

    **Strategic Rules (Think carefully):**
    1. If **Within Budget**: APPROVE immediately.
    2. If **Over Budget**: You must refine, BUT choose the "Lesser of Two Evils":
       - **Don't just pick the biggest saving.** Look at the Quality Trade-off.
       - If the Cheaper Flight adds 5+ hours of travel time for only €10 saving, REJECT IT.
       - If the Cheaper Hotel drops the rating from 9.0 to 6.0, try to avoid it unless necessary.
       - If both options are terrible (huge quality drop), pick the one that saves the most money to fix the budget.
       - If one option saves a lot of money with minimal quality loss (e.g., same flight duration, similar hotel rating), PICK THAT ONE.

    3. **Edge Case:** If the plan is slightly over budget (e.g., <5%) but the cheaper alternatives are terrible (bad ratings, long flights), you can APPROVE it. But explain why in the feedback (e.g., "Slightly over budget, but alternatives compromise quality too much").

    Make a decision: APPROVE, REFINE_FLIGHT, or REFINE_HOTEL.
    """

    try:
        ai_message = evaluator_llm.invoke(prompt)
        
        if not ai_message.tool_calls:
            print(f"Gemini Response (No Tool): {ai_message.content}")
            return {"evaluation_result": EvaluationResult(action="APPROVE", feedback="Auto-approved (Gemini didn't invoke tool)", total_cost=total_cost), "refinement_count": refinement_count + 1}
            
        tool_call = ai_message.tool_calls[0]
        result = EvaluationResult(**tool_call['args'])
        result.total_cost = total_cost
        
        print(f"-> Gemini Decision: {result.action}. Reason: {result.feedback}")
        return {"evaluation_result": result, "refinement_count": refinement_count + 1}

    except Exception as e:
        print(f"Gemini Error: {e}")
        return {"evaluation_result": EvaluationResult(action="APPROVE", feedback="Approved due to evaluator error.", total_cost=total_cost), "refinement_count": refinement_count + 1}



MAX_REFINEMENTS = 2

def should_refine_or_end(state: TripState):
    """
    Reads the action from the evaluation result to route the graph.
    """
    print("--- Routing based on Evaluation ---")
    action = state["evaluation_result"].action
    count = state.get('refinement_count', 0)

    if count >= MAX_REFINEMENTS:
        print(f"-> Maximum refinement count ({MAX_REFINEMENTS}) reached. Finishing.")
        return "end"
    
    if action == "APPROVE":
        print("-> Plan approved. Finishing.")
        return "end"
    
    if action == "REFINE_HOTEL":
        print(f"-> Plan hotel refinement required. Looping back to hotel_agent (Attempt {count}).")
        current_index = state['hotel_options'].index(state['selected_hotel'])

        if current_index + 1 < len(state['hotel_options']):
            state['selected_hotel'] = state['hotel_options'][current_index + 1]
        return "refine_hotel" 

    elif action == "REFINE_FLIGHT":
        print(f"-> Plan flight refinement required. Looping back to flight_agent (Attempt {count}).")
        current_index = state['flight_options'].index(state['selected_flight'])
        if current_index + 1 < len(state['flight_options']):
            state['selected_flight'] = state['flight_options'][current_index + 1]
        return "refine_flight"


def map_generator_node(state: TripState) -> dict:
    """Generates an interactive Folium map from the final itinerary and returns its HTML content."""
    print("--- Running Map Generator ---")
    final_itinerary = state.get("final_itinerary")

    if final_itinerary and final_itinerary.daily_plans:
        geocoded_count = sum(1 for day in final_itinerary.daily_plans for act in day.activities if act.latitude)
        print(f"-> Itinerary received. Found {geocoded_count} geocoded activities to plot on the map.")
    
    

    if not final_itinerary or not final_itinerary.daily_plans:
        return {"map_html": None} 

    first_coord = None
    all_coords = [] 
    for day in final_itinerary.daily_plans:
        for activity in day.activities:
            if activity.latitude and activity.longitude:
                coord = (activity.latitude, activity.longitude)
                all_coords.append(coord)
                if first_coord is None:
                    first_coord = coord
    
    if not first_coord:
        print("-> No coordinates found in the itinerary to create a map.")
        return {"map_html": None}

    m = folium.Map(location=first_coord, zoom_start=13)

    marker_cluster = folium.plugins.MarkerCluster().add_to(m)
    
    colors = ['blue', 'green', 'purple', 'orange', 'darkred', 'cadetblue', 'pink', 'lightgray']
    
    activity_counter = 1
    for i, day_plan in enumerate(final_itinerary.daily_plans):
        day_color = colors[i % len(colors)] 
        for activity in day_plan.activities:
            if activity.latitude and activity.longitude:
                popup_html = f"<b>Day {day_plan.day}: {activity.name}</b><br>{activity.description}"
                folium.Marker(
                    [activity.latitude, activity.longitude],
                    popup=popup_html,
                    tooltip=f"Day {day_plan.day} - {activity_counter}. {activity.name}",
                    icon=folium.Icon(color=day_color, icon='info-sign')
                ).add_to(marker_cluster) 
                activity_counter += 1

    if all_coords:
        m.fit_bounds(m.get_bounds())

    map_html_content = m._repr_html_()
    
    print(f"-> Interactive map HTML generated.")
    
    return {"map_html": map_html_content}



def report_formattor_node(state: TripState) -> dict:
    """Takes the final trip plan and generates a richly formatted Markdown report with all details."""
    print("--- Report Formatter is running ---")
    itinerary = state.get("final_itinerary")
    trip_plan = state.get("trip_plan")
    evaluation = state.get("evaluation_result")
    events = state.get("events")
    map_html_content = state.get("map_html") 
    
    if not itinerary or not trip_plan or not itinerary.selected_flight or not itinerary.selected_hotel:
        final_report_md = "# Trip Plan Could Not Be Generated\n\n"
        if not state.get("flight_options"):
            final_report_md += "- Sorry, no flights matching your criteria were found.\n"
        if not state.get("hotel_options"):
            final_report_md += "- Sorry, no hotels matching your criteria were found.\n"
        else:
            final_report_md += "A valid trip plan could not be generated with the available options. Please try modifying your request."
    else:
        def format_duration(minutes: int) -> str:
            if not minutes: return ""
            hours, mins = divmod(minutes, 60)
            return f"{hours}h {mins}m"
            
        def format_date(date_str: str) -> str:
            dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return dt_obj.strftime("%B %d, %Y")

        md = f"# Your Trip to {trip_plan.destination} ({format_date(trip_plan.start_date)} - {format_date(trip_plan.end_date)})\n\n"
        
        md += "## 📊 Budget Summary\n"
        total_cost = evaluation.total_cost
        budget = trip_plan.budget

        flight_and_hotel_cost = itinerary.selected_flight.price + itinerary.selected_hotel.total_price
        total_daily_spending = total_cost - flight_and_hotel_cost

        md += f"- **Flight + Hotel Cost:** €{flight_and_hotel_cost:,.2f}\n"
        if total_daily_spending > 0:
            md += f"- **Estimated Daily Spending (for {trip_plan.days} days):** €{total_daily_spending:,.2f}\n"
        md += f"------------------------------------\n"
        md += f"- **Total Estimated Cost:** €{total_cost:,.2f}\n"
        md += f"- **Your Total Budget:** €{budget:,.2f}\n\n"
        
        if total_cost <= budget:
            md += f"- **Status:** ✅ Plan is **€{budget - total_cost:,.2f} under budget**.\n\n"
        else:
            md += f"- **Status:** ⚠️ Plan is **€{total_cost - budget:,.2f} over budget**.\n\n"

        md += "## ✈️ Flight Information\n"
        flight = itinerary.selected_flight
        dep_leg = flight.departure_leg
        ret_leg = flight.return_leg
        
        md += f"**Airline:** {dep_leg.airline}\n"
        md += f"**Total Price (for {trip_plan.person} people):** €{flight.price:,.2f}\n\n"
        md += "|  | Time | Details | Airport |\n"
        md += "|:---|:---|:---|:---|\n"
        
        aircraft_dep = f"({dep_leg.aircraft_type})" if dep_leg.aircraft_type else ""
        details_depart = f"🛫 **{dep_leg.flight_number}** {aircraft_dep}"
        md += f"| **Depart**<br>*{format_date(trip_plan.start_date)}* | **{dep_leg.departure_time}** | {details_depart} | **{dep_leg.departure_airport}** |\n"
        md += f"| | *{format_duration(dep_leg.duration_minutes)}* | Total Journey | |\n"

        if dep_leg.is_layover:
            md += f"| | | *{format_duration(dep_leg.layover_duration_minutes)} Layover* | *at {dep_leg.layover_airport}* |\n"
        md += f"| | **{dep_leg.arrival_time}** | 🛬 Arriving At | **{dep_leg.arrival_airport}** |\n"
        md += "| | | | |\n"
        
        aircraft_ret = f"({ret_leg.aircraft_type})" if ret_leg.aircraft_type else ""
        details_return = f"🛫 **{ret_leg.flight_number}** {aircraft_ret}"
        md += f"| **Return**<br>*{format_date(trip_plan.end_date)}* | **{ret_leg.departure_time}** | {details_return} | **{ret_leg.departure_airport}** |\n"
        md += f"| | *{format_duration(ret_leg.duration_minutes)}* | Total Journey | |\n"

        if ret_leg.is_layover:
            md += f"| | | *{format_duration(ret_leg.layover_duration_minutes)} Layover* | *at {ret_leg.layover_airport}* |\n"
        md += f"| | **{ret_leg.arrival_time}** | 🛬 Arriving At | **{ret_leg.arrival_airport}** |\n\n"


        num_nights = (datetime.strptime(trip_plan.end_date, "%Y-%m-%d") - datetime.strptime(trip_plan.start_date, "%Y-%m-%d")).days
        hotel = itinerary.selected_hotel
        
        md += "## 🏨 Hotel Information\n"
        
        photo_url = hotel.main_photo_url
        if photo_url and "square60" in photo_url:
            photo_url = photo_url.replace("square60", "max500")
            
        if photo_url:
            md += f"![{hotel.hotel_name}]({photo_url})\n\n"
            
        md += f"### {hotel.hotel_name}\n"
        md += f"**Rating:** {hotel.rating} / 10.0 ({hotel.rating_word} based on {hotel.review_count} reviews)\n"
        md += f"**Taxes and Fees:** ~€{hotel.price_per_night:,.2f}\n" 
        md += f"**Total Price (for {num_nights} nights, {trip_plan.person} people):** €{hotel.total_price:,.2f}\n"
        
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={hotel.hotel_name.replace(' ', '+')}"
        md += f"- **Location:** [{hotel.hotel_name} on Google Maps]({google_maps_url})\n\n"


        if events:
            md += "---\n\n## 🎫 Events & Concerts During Your Stay\n"
            md += "| Date | Event | Venue |\n"
            md += "|:---|:---|:---|\n"
            for event in events:
                md += f"| {event.date} | **[{event.name}]({event.url})** | {event.venue} |\n"
            md += "\n"

        
        md += "---\n\n## 🗺️ Daily Itinerary\n"
        if not itinerary.daily_plans:
            md += "No specific activities planned for this trip."
        else:
            start_date_obj = datetime.strptime(trip_plan.start_date, "%Y-%m-%d")
            activity_counter = 1
            for day_plan in itinerary.daily_plans:
                current_date = start_date_obj + timedelta(days=day_plan.day - 1)
                md += f"\n### Day {day_plan.day} - {current_date.strftime('%B %d, %Y')}\n"
                for activity in day_plan.activities:
                    md += f"- **{activity.time_of_day}: {activity_counter}. {activity.name}**\n"
                    md += f"  - *{activity.description}*\n"
                
                    if activity.latitude and activity.longitude:
                        location_url = f"https://www.google.com/maps?q={activity.latitude},{activity.longitude}"
                        md += f"  - Location: [{activity.name}]({location_url})\n"
                    else:
                        location_url = f"https://www.google.com/maps?q={activity.name.replace(' ', '+')}+{trip_plan.destination.replace(' ', '+')}"
                        md += f"  - Location: [{activity.name}]({location_url})\n"
                
                    activity_counter += 1

        final_report_md = md

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    md_path = os.path.join(output_dir, "trip_itinerary.md")
    html_path = os.path.join(output_dir, "trip_itinerary.html")

    try:
        with open(md_path, "w", encoding="utf-8") as f: f.write(final_report_md)
        print(f"-> Markdown report saved to: {md_path}")
        
        css_style = """<style> 
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 2rem auto; padding: 2rem; background: linear-gradient(to right, #f8f9fa, #ffffff); border: 1px solid #e1e1e1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 8px; } 
            h1, h2, h3 { color: #2c3e50; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; } 
            h1 { font-size: 2.5em; text-align: center; } 
            h2 { font-size: 2em; } 
            code { background-color: #ecf0f1; padding: 2px 5px; border-radius: 4px; font-size: 0.9em; } 
            .map-container { margin-top: 30px; border-top: 2px solid #f0f0f0; padding-top: 20px; }
            iframe { width: 100%; height: 500px; border: none; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        </style>"""

        html_body = markdown2.markdown(final_report_md, extras=["tables", "fenced-code-blocks"])

        full_html = f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>AI Trip Plan</title>{css_style}</head><body>{html_body}</body></html>'
        with open(html_path, "w", encoding="utf-8") as f: f.write(full_html)
        print(f"-> HTML report saved to: {html_path}")
    except Exception as e:
        print(f"An error occurred while saving files: {e}")

    return {
        "markdown_report": final_report_md,
        "map_html": map_html_content 
    }