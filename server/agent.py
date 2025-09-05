import os
import operator
from dotenv import load_dotenv
from typing import Annotated, List, Optional, Dict, Literal
from typing_extensions import TypedDict
import markdown2
import json
import requests
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool
from langchain_tavily import TavilySearch



load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")
tavily_api_key = os.getenv("TAVILY_API_KEY")
rapidapi_key = os.getenv("RAPIDAPI_KEY")

if not all([groq_api_key, tavily_api_key, rapidapi_key]):
    raise ValueError("One or more required API keys are missing from the .env file!")


llm = ChatGroq(model="llama-3.3-70b-versatile", api_key = groq_api_key, max_retries=3)


class TripRequest(BaseModel) :
    """Schema for user's travel requests."""
    origin: str = Field(description="The departure city for the trip.")
    destination: str = Field(description="The arrival city for the trip.")
    start_date: str = Field(description="The start date of the trip in YYYY-MM-DD format.")
    end_date: str = Field(description="The end date of the trip in YYYY-MM-DD format.")
    person: int = Field(description="The total number of people participating in the trip.")
    budget: Optional[float] = Field(description="The estimated budget for the trip.")
    interests: Optional[List[str]] = Field(description="A list of interests for the trip, e.g., ['art', 'history', 'food'].")

    @property
    def days(self) -> int:
        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")
        return (end - start).days + 1


class FlightLeg(BaseModel):
    """Schema for a single leg of a flight (either departure or return)."""
    departure_time: str = Field(description="Departure time in HH:MM format.")
    arrival_time: str = Field(description="Arrival time in HH:MM format.")
    departure_airport: str = Field(description="Full name and IATA code of the departure airport.")
    arrival_airport: str = Field(description="Full name and IATA code of the arrival airport.")
    duration_minutes: int = Field(description="Duration of this specific leg in minutes.")
    airline: str = Field(description="The name of the airline for this leg.")
    flight_number: str = Field(description="The flight number, e.g., 'TK1857'.")
    aircraft_type: str = Field(description="The type of aircraft, e.g., 'Boeing 737'.")
    is_layover: bool = Field(default=False, description="True if this journey has a layover.")
    layover_airport: Optional[str] = Field(default=None, description="The airport where the layover occurs.")
    layover_duration_minutes: Optional[int] = Field(default=None, description="The duration of the layover in minutes.")


class FlightInfo(BaseModel):
    """Schema for flight information, now with detailed legs."""
    price: float = Field(description="The total price of the round-trip flight for all passengers.")
    departure_leg: FlightLeg
    return_leg: FlightLeg
    total_duration_minutes: int = Field(description="The total round-trip duration in minutes.")


class FlightSelection(BaseModel):
    """Schema for the selected flight."""
    best_option_index: int = Field(description="The index (starting from 0) of the best flight option from the provided list.")
    reasoning: str = Field(description="A brief explanation of why this option was chosen.")


class HotelInfo(BaseModel):
    """Schema for hotel information."""
    hotel_name: str = Field(description="The name of the hotel.")
    price_per_night: float = Field(description="The price per night.")
    total_price: float = Field(description="The total price for the entire stay.")
    rating: float = Field(description="The hotel's rating out of 9.")
    review_count: int = Field(description="Total number of reviews for the hotel.")
    rating_word: str = Field(description="The rating described as a word, e.g., 'Exceptional'.")
    main_photo_url: Optional[str] = Field(default=None, description="URL of the hotel's main photo.")
    static_map_url: Optional[str] = Field(default=None, description="URL of a static map image showing the hotel's location.")


class HotelSelection(BaseModel):
    """Schema for the selected hotel."""
    best_option_index: int = Field(description="The index (starting from 0) of the best hotel option from the provided list.")
    reasoning: str = Field(description="A brief explanation of why this hotel was chosen, balancing price and rating.")


class Activity(BaseModel):
    """Schema for a single activity."""
    name: str = Field(description="Name of the activity or place.")
    description: str = Field(description="A brief description of the activity.")
    location: str = Field(description="Location or address of the activity.")
    time_of_day: str = Field(description="Suggested time of day, e.g., 'Morning', 'Afternoon', 'Evening'.")


class ExtractedActivities(BaseModel):
    """Schema for the list of extracted activities."""
    activities: List[Activity]


class DailyPlan(BaseModel):
    """Schema for a single day's plan."""
    day: int = Field(description="The day number (e.g., 1, 2, 3).")
    activities: List[Activity] = Field(description="A list of activities for the day.")


class ScheduledActivities(BaseModel):
    """The daily schedule of activities for the trip."""
    daily_plans: List[DailyPlan]



class Itinerary(BaseModel):
    """The complete, final itinerary for the trip."""
    selected_flight: FlightInfo
    selected_hotel: HotelInfo
    daily_plans: List[DailyPlan]


class EvaluationResult(BaseModel):
    """Schema for the evaluation result."""
    action: Literal["APPROVE", "REFINE_HOTEL", "REFINE_FLIGHT"] = Field(description="Action to take.")
    feedback: str = Field(description="Feedback on the plan, explaining the reason for the action.")
    total_cost: float = Field(description="The calculated total cost of the trip.")



class TripState(TypedDict):
    user_request: str
    trip_plan: Optional[TripRequest]
    selected_flight: Optional[FlightInfo] 
    flight_options: List[FlightInfo] 
    selected_hotel: Optional[HotelInfo]
    hotel_options: List[HotelInfo]
    extracted_activities: Optional[List[Activity]]
    final_itinerary: Optional[Itinerary]
    evaluation_result: Optional[EvaluationResult] 
    refinement_count: int 
    markdown_report: Optional[str]


@tool
def iata_finder_tool(city_name: str) -> List[str]:
    """
    Finds the IATA codes for a given city name using the Booking-com18 auto-complete endpoint.
    Returns a list of relevant airport IATA codes.
    """
    print(f"--- Calling Booking.com auto-complete API for {city_name} ---")
    
    url = "https://booking-com18.p.rapidapi.com/flights/v2/auto-complete"
    querystring = {"query": city_name}
    headers = {
        "x-rapidapi-key": os.getenv("RAPIDAPI_KEY"),
        "x-rapidapi-host": "booking-com18.p.rapidapi.com"
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()
        
        iata_codes = []
        if data.get('data'):
            for location in data['data']:
                if location.get('type') == 'AIRPORT':
                    iata_codes.append(location['code'])
        
        if not iata_codes:
            print(f"-> No IATA codes found for {city_name}")
            return []
            
        print(f"-> Found IATA codes for {city_name}: {iata_codes}")
        return iata_codes
        
    except requests.exceptions.RequestException as e:
        print(f"-> IATA Finder API request failed: {e}")
        return []


@tool
def flight_search_tool(origin_iata_list: List[str], destination_iata_list: List[str], start_date: str, end_date: str, person: int, origin_city: str, destination_city: str) -> List[FlightInfo]:
    """
    Searches for flights and robustly extracts detailed leg information from the complex API response structure.
    """
    print(f"--- Calling REAL Flight API for {origin_iata_list} -> {destination_iata_list} ---")
    all_flight_options = []


    def _parse_journey_segment(segment: dict) -> Optional[FlightLeg]:
        try:
            legs = segment.get('legs', [])
            if not legs: return None
            
            departure_airport_info = segment.get('departureAirport')
            arrival_airport_info = segment.get('arrivalAirport')
            total_duration_minutes = segment.get('totalTime', 0) // 60
            
            first_leg_data = legs[0]
            last_leg_data = legs[-1]

            departure_at_str = first_leg_data.get('departureTime')
            arrival_at_str = last_leg_data.get('arrivalTime')
            carrier_data = first_leg_data.get('carriersData', [{}])[0]
            flight_info = first_leg_data.get('flightInfo', {})
            flight_number = flight_info.get('flightNumber', '')
            aircraft_type = segment.get('aircraftType', '') 

            if not all([departure_at_str, arrival_at_str, departure_airport_info, arrival_airport_info, carrier_data]):
                return None

            departure_time = datetime.fromisoformat(departure_at_str).strftime('%I:%M %p')
            arrival_time = datetime.fromisoformat(arrival_at_str).strftime('%I:%M %p')
            departure_airport = f"{departure_airport_info.get('name')} ({departure_airport_info.get('code')})"
            arrival_airport = f"{arrival_airport_info.get('name')} ({arrival_airport_info.get('code')})"
            airline = carrier_data.get('name', 'Unknown Airline')

            is_layover = len(legs) > 1
            layover_airport = None
            layover_duration_minutes = None

            if is_layover:

                layover_airport_info = first_leg_data.get('arrivalAirport')
                layover_airport = f"{layover_airport_info.get('name')} ({layover_airport_info.get('code')})"
                
                first_leg_arrival = datetime.fromisoformat(first_leg_data.get('arrivalTime'))
                second_leg_departure = datetime.fromisoformat(legs[1].get('departureTime'))
                layover_duration_minutes = int((second_leg_departure - first_leg_arrival).total_seconds() / 60)

            return FlightLeg(
                departure_time=departure_time, arrival_time=arrival_time,
                departure_airport=departure_airport, arrival_airport=arrival_airport,
                duration_minutes=total_duration_minutes,
                airline=airline,
                flight_number=f"{carrier_data.get('code', '')}{flight_number}",
                aircraft_type=aircraft_type,
                is_layover=is_layover,
                layover_airport=layover_airport,
                layover_duration_minutes=layover_duration_minutes
            )
        except Exception as e:
            print(f"      -> Warning: Skipping a journey segment due to a parsing error: {e}")
            return None


    for origin_iata in origin_iata_list:
        for destination_iata in destination_iata_list:
            print(f"-> Searching flights from {origin_iata} to {destination_iata}...")

            url = "https://booking-com18.p.rapidapi.com/flights/v2/search-roundtrip"
            querystring = {
                "departId": origin_iata, "arrivalId": destination_iata, "departDate": start_date,
                "returnDate": end_date, "adults": str(person), "sort": "CHEAPEST", "currency_code": "EUR"
            }
            headers = { "x-rapidapi-key": os.getenv("RAPIDAPI_KEY"), "x-rapidapi-host": "booking-com18.p.rapidapi.com" }

            try:
                response = requests.get(url, headers=headers, params=querystring)
                response.raise_for_status()
                data = response.json()

                offers = data.get('data', {}).get('flightOffers', []) or data.get('data', {}).get('flights', [])

                for offer in offers:
                    price_info = offer.get('priceBreakdown', {}).get('total', {})
                    total_price = price_info.get('units', 0) + price_info.get('nanos', 0) / 1e9

                    segments = offer.get('segments')
                    if not segments or len(segments) < 2: continue

                    departure_leg = _parse_journey_segment(segments[0])
                    return_leg = _parse_journey_segment(segments[1])
                    
                    if not departure_leg or not return_leg:
                        continue
                    
                    total_duration = departure_leg.duration_minutes + return_leg.duration_minutes

                    all_flight_options.append(FlightInfo(
                        price=total_price,
                        departure_leg=departure_leg,
                        return_leg=return_leg,
                        total_duration_minutes=total_duration
                    ))
            except Exception as e:
                print(f"-> API request failed for {origin_iata} -> {destination_iata}: {e}")
                continue

    if not all_flight_options:
        print("-> No valid flights parsed from the response.")
        return []

    all_flight_options.sort(key=lambda x: x.price)
    print(f"-> Found and successfully parsed {len(all_flight_options)} valid flights. Returning the top 5 cheapest.")
    return all_flight_options[:5]


@tool
def location_id_finder_tool(city_name: str) -> Optional[str]:
    """Finds the specific locationId for a city using the Booking.com Stays auto-complete API.
    Returns the ID for the first and most relevant result."""
    print(f"--- Calling Location ID Finder API for {city_name} ---")
    
    url = "https://booking-com18.p.rapidapi.com/stays/auto-complete"
    querystring = {"query": city_name}
    headers = {"x-rapidapi-key": rapidapi_key, "x-rapidapi-host": "booking-com18.p.rapidapi.com"}
    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()
        if data.get('data') and len(data['data']) > 0:
            location_id = data['data'][0].get('id')
            if location_id:
                print(f"-> Found Location ID for {city_name}: {location_id}")
                return location_id
        print(f"-> No Location ID found for {city_name}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"-> Location ID Finder API request failed: {e}")
        return None
    except (KeyError, TypeError, ValueError) as e:
        print(f"-> Error processing location ID data: {e}")
        return None


@tool
def hotel_search_tool(location_id: str, start_date: str, end_date: str, person: int) -> List[HotelInfo]:
    """
    Searches for top hotels and extracts rich details for each option.
    """
    print(f"--- Calling REAL Booking.com Hotel API with Location ID: {location_id[:30]}... ---")
    
    url = "https://booking-com18.p.rapidapi.com/stays/search"
    querystring = {
        "locationId": location_id,
        "checkinDate": start_date,
        "checkoutDate": end_date,
        "adults": str(person),
        "sortBy": "bayesian_review_score", 
        "currencyCode": "EUR"
    }
    headers = {
        "x-rapidapi-key": os.getenv("RAPIDAPI_KEY"),
        "x-rapidapi-host": "booking-com18.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()

        if not data.get('data'):
            print("-> No hotels found in the API response.")
            return []

        results = []
        num_nights = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
        
        for hotel_data in data.get('data', [])[:5]:

            price_breakdown = hotel_data.get('priceBreakdown', {})

            total_price = price_breakdown.get('grossPrice', {}).get('value', 0)
            price_per_night = price_breakdown.get('excludedPrice', {}).get('value', 0)
            
            hotel_id = hotel_data.get('id')

            photo_url = None
            if hotel_data.get('photoUrls'):
                photo_url = hotel_data['photoUrls'][0]

            static_map_url = None
            lat = hotel_data.get('latitude')
            lon = hotel_data.get('longitude')
            
            if lat and lon:
                static_map_url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=15&size=600x300&marker={lat},{lon},red-pushpin"
            
            results.append(
                HotelInfo(
                    hotel_name=hotel_data.get('name', 'Unknown Hotel'),
                    price_per_night=round(price_per_night, 2),
                    total_price=total_price,
                    rating=hotel_data.get('reviewScore', 0),
                    review_count=hotel_data.get('reviewCount', 0),
                    rating_word=hotel_data.get('reviewScoreWord', ''),
                    main_photo_url=photo_url,
                    static_map_url=static_map_url
                )
            )
        
        print(f"-> Found and parsed {len(results)} hotel options from API.")
        return results

    except Exception as e:
        print(f"-> Hotel search or parsing failed: {e}")
        return []



@tool
def activity_finder_tool(destination: str, interests: List[str]) -> str:
    """
    Performs targeted Tavily searches and returns a consolidated summary string,
    handling different library version outputs.
    """
    print(f"--- Calling Tavily Search with targeted queries for {destination} ---")
    all_results_summary = ""
    tavily_search = TavilySearch(max_results=4, api_key=tavily_api_key)
    
    for interest in interests:
        query = f"specific and famous '{interest}' places, landmarks, or experiences in {destination}. Give me names of places, not tours."
        print(f"-> Searching for: {query}")
        
        try:
            response_data = tavily_search.invoke(query)
            
            search_results = []
            if isinstance(response_data, dict):
                print("-> Tavily response type: dict (Old format). Extracting 'results' key.")
                search_results = response_data.get('results', [])
            elif isinstance(response_data, list):
                print("-> Tavily response type: list (New format).")
                search_results = response_data
            else:
                print(f"-> WARNING: Tavily returned an unexpected data type: {type(response_data)}")

            all_results_summary += f"\n--- Search Results for '{interest}' in {destination} ---\n"

            if not search_results:
                all_results_summary += "No specific results found for this interest.\n\n"
                continue

            for result in search_results:
                if isinstance(result, dict):
                    all_results_summary += f"Title: {result.get('title', 'N/A')}\nContent: {result.get('content', 'No content')}\n\n"
                else:
                    all_results_summary += f"Unexpected item in results: {result}\n\n"

        except Exception as e:
            print(f"-> An unexpected error occurred in activity_finder_tool: {e}")

    if not all_results_summary.strip() or "No specific results found" in all_results_summary:
         print("-> WARNING: Tavily search ran but did not produce usable activity content.")
         return "No relevant activities found from web search."
         
    return all_results_summary



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
    Orchestrates the flight search: finds IATA codes, then finds flight options,
    and finally uses an LLM to make an intelligent selection.
    """
    print("--- Running Flight Agent ---")

    trip_plan = state['trip_plan']

    if not trip_plan:
         return {}

    print("-> Step 1: Finding IATA codes...")

    origin_iatalist = iata_finder_tool.invoke(trip_plan.origin)
    destination_iatalist = iata_finder_tool.invoke(trip_plan.destination)

    if not origin_iatalist or not destination_iatalist:
        print("-> WARNING: No IATA codes found for origin or destination city.")
        return {"flight_options": [], "selected_flight": None}


    print("-> Step 2: Finding flight options...")
    flight_options = flight_search_tool.invoke({
        "origin_iata_list": origin_iatalist,
        "destination_iata_list": destination_iatalist,
        "start_date": trip_plan.start_date,
        "end_date": trip_plan.end_date,
        "person": trip_plan.person,
        "origin_city": trip_plan.origin,
        "destination_city": trip_plan.destination
    })

    
    if not flight_options:
        print("-> No flights found. Updating state to reflect failure.")
        return {"flight_options": [], "selected_flight": None}

    
    print("-> Step 3: LLM making intelligent selection...")
    selection_llm = llm.bind_tools([FlightSelection])

    
    options_text = ""
    for i, opt in enumerate(flight_options):
        airline = opt.departure_leg.airline
        total_duration = opt.total_duration_minutes
        options_text += f"Option {i}: Airline: {airline}, Price: €{opt.price:.2f}, Total Duration: {total_duration} minutes.\n"

    prompt = f"""
    You are an expert travel agent. Your task is to select the best flight from the list below.
    The user is budget-conscious but also values their time. Find the best balance between price and duration.
    A slightly more expensive flight that is significantly faster is often a better choice.

    USER PREFERENCES:
    - Budget: €{trip_plan.budget}

    FLIGHT OPTIONS:
    {options_text}

    Analyze the options and decide which one offers the best value. Call the `FlightSelection` function with your decision.
    """

    ai_message = selection_llm.invoke(prompt)

    selected_flight = None

    if not ai_message.tool_calls:
        print("-> WARNING: LLM failed to select a flight on the first try. Defaulting to the cheapest option.")
        selected_flight = flight_options[0]

    else:
        tool_call = ai_message.tool_calls[0]
        selection = FlightSelection(**tool_call['args'])
        
        if selection.best_option_index >= len(flight_options):
            print(f"-> WARNING: LLM selected an invalid index. Defaulting to cheapest option.")
            selected_flight = flight_options[0]
        else:
            selected_flight = flight_options[selection.best_option_index]
            print(f"-> LLM reasoning for flight choice: {selection.reasoning}")


    if selected_flight:
        print(f"-> LLM selected flight: {selected_flight.departure_leg.airline} for €{selected_flight.price}")

     
    return {"flight_options": flight_options, "selected_flight": selected_flight}


def hotel_agent(state: TripState) -> dict:
    """Finds hotel options and then makes a smart choice based on price, rating, and budget balance."""
    print("--- Hotel Agent is running ---")
    trip_plan = state['trip_plan']
    if not trip_plan: return {}
    
    
    if state.get("hotel_options") and len(state.get("hotel_options", [])) > 1:
        print("-> Refinement loop. Using existing hotel list.")
        hotel_options = state["hotel_options"]
    else:
        print("-> Step 1: Finding location ID...")
        location_id = location_id_finder_tool.invoke(trip_plan.destination)
        if not location_id:
            print(f"-> FAILED: No location ID found for {trip_plan.destination}.")
            return {"hotel_options": [], "selected_hotel": None}

        print("-> Step 2: Finding hotel options...")
        hotel_options = hotel_search_tool.invoke({
            "location_id": location_id, "start_date": trip_plan.start_date,
            "end_date": trip_plan.end_date, "person": trip_plan.person
        })
        if not hotel_options:
            print(f"-> FAILED: No hotels found for {trip_plan.destination}.")
            return {"hotel_options": [], "selected_hotel": None}

    print("-> Step 3: LLM making a smart selection...")
    
   
    
    selection_llm = llm.bind_tools([HotelSelection])
    options_text = "".join([f"Option {i}: Name: {opt.hotel_name}, Rating: {opt.rating}/10, Total Price: €{opt.total_price:.2f}\n" for i, opt in enumerate(hotel_options)])

    refinement_feedback = ""
    if state.get("refinement_count", 0) > 0 and state.get("evaluation_result"):

        refinement_feedback = f"The previous attempt exceeded the budget. Feedback: '{state['evaluation_result'].feedback}'. Please focus on finding a more budget-friendly yet still good option this time."


    prompt = f"""
    You are an expert travel advisor. Your task is to select the best hotel for the user from the list below.
    {refinement_feedback}
    The user cares about their budget. Find the best balance between a high rating and a price that reasonably fits the user's budget.
    A super high-rated hotel that is far too expensive and consumes most of the budget is a bad choice.

    USER PREFERENCES:
    - Budget: €{trip_plan.budget}

    HOTEL OPTIONS:
    {options_text}

    Analyze the options based on both rating and price. Select the hotel that offers the best value for money.
    Report your decision by calling the `HotelSelection` function.
    """

    ai_message = selection_llm.invoke(prompt)
    if not ai_message.tool_calls:
        raise ValueError("LLM could not select a hotel.")
        
    tool_call = ai_message.tool_calls[0]
    selection = HotelSelection(**tool_call['args'])
    
    if selection.best_option_index >= len(hotel_options):
        print(f"-> WARNING: LLM selected an invalid index ({selection.best_option_index}). Using the first option instead.")
        selection.best_option_index = 0
        
    selected_hotel = hotel_options[selection.best_option_index]
    print(f"-> LLM reasoning for hotel selection: {selection.reasoning}")
    print(f"-> LLM selected hotel: {selected_hotel.hotel_name}")
    
    return {"hotel_options": hotel_options, "selected_hotel": selected_hotel}



def activity_extraction_agent(state: TripState) -> dict:
    """
    Analyzes the raw text from Tavily and extracts a structured list of activities.
    """
    print("--- Running Activity Extraction Agent ---")
    
    raw_activity_data = activity_finder_tool.invoke({
        "destination": state["trip_plan"].destination,
        "interests": state["trip_plan"].interests
    })

    if not raw_activity_data or not raw_activity_data.strip():
        print("-> No text from web search to extract activities from.")
        return {"extracted_activities": []}

    
    extraction_llm = llm.bind_tools([ExtractedActivities])
    
    prompt = f"""
    You are a data extraction expert. Your task is to analyze the provided text from a web search
    and extract all specific, real-world places, landmarks, or experiences mentioned.

    CRITICAL INSTRUCTIONS:
    - Focus only on concrete nouns (e.g., 'Rijksmuseum', 'Anne Frank House').
    - Ignore generic suggestions like 'explore the city' or 'go on a food tour'.
    - For each extracted activity, create a structured object with `name`, `description`, `location`, and a suitable `time_of_day`.
    - The location should be the city name: "{state['trip_plan'].destination}"

    RAW SEARCH RESULTS:
    ---
    {raw_activity_data}
    ---

    Now, call the `ExtractedActivities` function with the list of all the activities you found.
    """
    
    ai_message = extraction_llm.invoke(prompt)
    if not ai_message.tool_calls:
        print("-> LLM failed to extract any activities.")
        return {"extracted_activities": []}
        
    tool_call = ai_message.tool_calls[0]
    extracted = ExtractedActivities(**tool_call['args'])
    
    print(f"-> Extracted {len(extracted.activities)} specific activities.")
    return {"extracted_activities": extracted.activities}



def activity_scheduling_agent(state: TripState) -> dict:
    """
    Takes a clean list of activities and asks the LLM to schedule them into daily plans.
    Then, it manually combines this schedule with flight and hotel info to create the final itinerary.
    """
    print("--- Running Activity Scheduling Agent ---")
    trip_plan = state['trip_plan']
    selected_flight = state['selected_flight']
    selected_hotel = state['selected_hotel']
    activities = state['extracted_activities'] 

    if not all([trip_plan, selected_flight, selected_hotel]):
        print("-> Missing data, cannot schedule.")
        return {"final_itinerary": None} 
    if not activities:
        print("-> No activities to schedule. Creating an itinerary with only flight and hotel.")
        itinerary = Itinerary(selected_flight=selected_flight, selected_hotel=selected_hotel, daily_plans=[])
        return {"final_itinerary": itinerary}

    planner_llm = llm.bind_tools([ScheduledActivities])
    
    prompt = f"""
    You are an expert travel planner. Your sole task is to organize the following list of activities into a logical daily schedule for a {trip_plan.days}-day trip.

    CRITICAL INSTRUCTIONS:
    - Distribute the activities logically and evenly across the {trip_plan.days} days.
    - The final output MUST be a single, valid JSON object that perfectly matches the `ScheduledActivities` schema, containing only the 'daily_plans' field.

    LIST OF PRE-APPROVED ACTIVITIES TO SCHEDULE:
    {json.dumps([act.model_dump() for act in activities])}

    Now, create the `ScheduledActivities` JSON object.
    """
    
    ai_message = planner_llm.invoke(prompt)
    if not ai_message.tool_calls:
        raise ValueError("LLM failed to create an activity schedule.")
        
    tool_call = ai_message.tool_calls[0]
    scheduled_activities = ScheduledActivities(**tool_call['args'])
    
    final_itinerary = Itinerary(
        selected_flight=selected_flight,
        selected_hotel=selected_hotel,
        daily_plans=scheduled_activities.daily_plans
    )
    
    print("-> Final Itinerary Assembled Successfully.")
    return {"final_itinerary": final_itinerary}




def evaluator_agent(state: TripState) -> dict:
    """
    Evaluates the plan with a more strategic, value-based reasoning process.
    It considers the trade-offs of refining flight vs. hotel.
    """
    print("--- Running Smart Evaluator Agent ---")
    trip_plan = state['trip_plan']
    selected_flight = state['selected_flight']
    selected_hotel = state['selected_hotel']
    flight_options = state['flight_options']
    hotel_options = state['hotel_options']

    if not all([trip_plan, selected_flight, selected_hotel]):
        return { "evaluation_result": EvaluationResult(action="APPROVE", feedback="Could not evaluate due to missing data.", total_cost=0) }
        
    total_cost = selected_flight.price + selected_hotel.total_price
    budget = trip_plan.budget

    refinement_count = state.get('refinement_count', 0)
    
    next_hotel_details = "No other hotel options available."
    potential_hotel_saving = 0
    if len(hotel_options) > refinement_count + 1:
        next_hotel = hotel_options[refinement_count + 1]
        potential_hotel_saving = selected_hotel.total_price - next_hotel.total_price
        next_hotel_details = next_hotel.model_dump_json(indent=2)

    next_flight_details = "No other flight options available."
    potential_flight_saving = 0
    if len(flight_options) > refinement_count + 1:
        next_flight = flight_options[refinement_count + 1]
        potential_flight_saving = selected_flight.price - next_flight.price
        next_flight_details = next_flight.model_dump_json(indent=2)
    
    evaluator_llm = llm.bind_tools([EvaluationResult])
    
    prompt = f"""
    You are a strategic travel consultant. Your goal is to find the OPTIMAL plan for the user, balancing budget, quality, and convenience. Analyze the provided data and choose the most logical action.

    **Data Analysis:**
    - User's Budget: €{budget}
    - Current Total Cost: €{total_cost}
    - Is plan over budget? {'Yes' if total_cost > budget else 'No'}

    **Current Selections:**
    - Selected Flight: {selected_flight.model_dump_json(indent=2)}
    - Selected Hotel: {selected_hotel.model_dump_json(indent=2)}

    **Potential Refinement Options:**
    - Next Cheaper Hotel Option: {next_hotel_details}
      (This change would save approximately €{potential_hotel_saving:.2f})
      
    - Next Cheaper Flight Option: {next_flight_details}
      (This change would save approximately €{potential_flight_saving:.2f})

    **Decision Rules:**
    1.  If the plan is within budget, 'APPROVE' it unless there's an alternative that offers a clear and significant upgrade for a very small price increase.
    2.  If the plan is over budget, you MUST choose a 'REFINE' action. To decide which one, consider the trade-offs:
        -   Don't just pick the one with the highest monetary saving.
        -   Analyze the **value**: Is the hotel saving large but comes with a huge drop in rating? Is the flight saving smaller but has almost no downside (e.g., same airline, slightly longer duration)?
        -   Choose the refinement (`REFINE_HOTEL` or `REFINE_FLIGHT`) that provides the **best overall value improvement for the user**.
    3.  If the plan is over budget but no cheaper options are available, 'APPROVE' but state the reason in your feedback.

    Based on these rules, call the `EvaluationResult` function with your decision and a clear reasoning.
    """
    
    ai_message = evaluator_llm.invoke(prompt)
    
    if not ai_message.tool_calls:
        raise ValueError("LLM failed to produce a valid tool call for the EvaluationResult.")
        
    tool_call = ai_message.tool_calls[0]
    result = EvaluationResult(**tool_call['args'])
   
    result.total_cost = total_cost
    print(f"-> Evaluator's strategic decision: {result.action}. Feedback: {result.feedback}")
    
    new_refinement_count = refinement_count + 1
    return {"evaluation_result": result, "refinement_count": new_refinement_count}



MAX_REFINEMENTS = 3

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


def report_formatter_node(state: TripState) -> dict:
    """Takes the final trip plan and generates a richly formatted Markdown report with all details."""
    print("--- Report Formatter is running ---")
    itinerary = state.get("final_itinerary")
    trip_plan = state.get("trip_plan")
    evaluation = state.get("evaluation_result")
    
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
        total_cost_per_person = total_cost / trip_plan.person if trip_plan.person > 0 else 0
        md += f"- **Your Budget:** €{budget:,.2f}\n"
        md += f"- **Total Estimated Cost:** €{total_cost:,.2f}\n"
        md += f"- **Estimated Cost Per Person:** €{total_cost_per_person:,.2f}\n"
        if total_cost <= budget:
            md += f"- **Status:** ✅ Congratulations! Your plan is **€{budget - total_cost:,.2f} under budget**.\n\n"
        else:
            md += f"- **Status:** ⚠️ Warning! Your plan is **€{total_cost - budget:,.2f} over budget**.\n\n"
        md += f"A {trip_plan.days}-day trip for {trip_plan.person} people, focused on {', '.join(trip_plan.interests)}.\n\n"

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
        
        if hotel.main_photo_url:
            large_photo_url = hotel.main_photo_url.replace('square60', 'square400')
            md += f"![{hotel.hotel_name}]({large_photo_url})\n\n"
            
        md += f"### {hotel.hotel_name}\n"
        md += f"**Rating:** {hotel.rating} / 10.0 ({hotel.rating_word} based on {hotel.review_count} reviews) <br>"
        md += f"**Taxes and Fees:** ~€{hotel.price_per_night:,.2f} <br>" 
        md += f"**Total Price (for {num_nights} nights, {trip_plan.person} people):** €{hotel.total_price:,.2f}\n\n"
        md += "\n"

        if hotel.static_map_url:
            interactive_map_url = f"https://www.google.com/maps/search/?api=1&query={hotel.hotel_name.replace(' ', '+')}"
            
            md += "#### Location\n"
            md += f"[![Map of {hotel.hotel_name}]({hotel.static_map_url})]({interactive_map_url})\n\n"

        
        md += "---\n\n## 🗺️ Daily Itinerary\n"
        if not itinerary.daily_plans:
            md += "No specific activities planned for this trip."
        else:
            start_date_obj = datetime.strptime(trip_plan.start_date, "%Y-%m-%d")
            for day_plan in itinerary.daily_plans:
                current_date = start_date_obj + timedelta(days=day_plan.day - 1)
                md += f"\n### Day {day_plan.day} - {current_date.strftime('%B %d, %Y')}\n"
                for activity in day_plan.activities:
                    md += f"- **{activity.time_of_day}: {activity.name}**\n"
                    md += f"  - *{activity.description}*\n"
                    md += f"  - Location: {activity.location}\n"
        final_report_md = md

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    md_path = os.path.join(output_dir, "trip_itinerary.md")
    html_path = os.path.join(output_dir, "trip_itinerary.html")
    try:
        with open(md_path, "w", encoding="utf-8") as f: f.write(final_report_md)
        print(f"-> Markdown report saved to: {md_path}")
        
        css_style = """<style> body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 2rem auto; padding: 2rem; background-color: #fdfdfd; border: 1px solid #e1e1e1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 8px; } h1, h2, h3 { color: #2c3e50; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; } h1 { font-size: 2.5em; text-align: center; } h2 { font-size: 2em; } code { background-color: #ecf0f1; padding: 2px 5px; border-radius: 4px; font-size: 0.9em; } </style>"""
        html_body = markdown2.markdown(final_report_md, extras=["tables", "fenced-code-blocks"])
        full_html = f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>AI Trip Plan</title>{css_style}</head><body>{html_body}</body></html>'
        with open(html_path, "w", encoding="utf-8") as f: f.write(full_html)
        print(f"-> HTML report saved to: {html_path}")
    except Exception as e:
        print(f"An error occurred while saving files: {e}")

    return {"markdown_report": final_report_md}


workflow = StateGraph(TripState)


workflow.add_node("planner_agent", planner_agent)
workflow.add_node("flight_agent", flight_agent)
workflow.add_node("hotel_agent", hotel_agent) 
workflow.add_node("activity_extraction_agent", activity_extraction_agent)
workflow.add_node("activity_scheduling_agent", activity_scheduling_agent)
workflow.add_node("evaluator_agent", evaluator_agent)
workflow.add_node("report_formatter_node", report_formatter_node) 


workflow.add_edge(START, "planner_agent")

workflow.add_edge("planner_agent", "flight_agent")
workflow.add_edge("planner_agent", "hotel_agent")

workflow.add_edge("flight_agent", "activity_extraction_agent")
workflow.add_edge("hotel_agent", "activity_extraction_agent")


workflow.add_edge("activity_extraction_agent", "activity_scheduling_agent")
workflow.add_edge("activity_scheduling_agent", "evaluator_agent")

workflow.add_conditional_edges(
    "evaluator_agent",
    should_refine_or_end,
    {
        "refine_hotel": "hotel_agent",           
        "refine_flight": "flight_agent",         
        "end": "report_formatter_node"           
    }
)

workflow.add_edge("report_formatter_node", END)


app = workflow.compile()


