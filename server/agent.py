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

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from folium import plugins


load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")
tavily_api_key = os.getenv("TAVILY_API_KEY")
rapidapi_key = os.getenv("RAPIDAPI_KEY")
ticketmaster_api_key = os.getenv("TICKETMASTER_API_KEY")


if not all([groq_api_key, tavily_api_key, rapidapi_key, ticketmaster_api_key]):
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
    daily_spending_budget: Optional[float] = Field(description="The estimated daily spending budget per person for activities, food, etc.")

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
    latitude: Optional[float] = Field(default=None, description="The latitude of the activity location.")
    longitude: Optional[float] = Field(default=None, description="The longitude of the activity location.")


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


class EventInfo(BaseModel):
    """Schema for a single event."""
    name: str = Field(description="The name of the event.")
    date: str = Field(description="The date of the event in YYYY-MM-DD format.")
    venue: str = Field(description="The name of the venue where the event is held.")
    url: str = Field(description="A direct URL to the event page for more details and tickets.")


class SelectedEvents(BaseModel):
    """A selected list of the most relevant events for the user."""
    events: List[EventInfo]


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
    events: Optional[List[EventInfo]]
    final_itinerary: Optional[Itinerary]
    evaluation_result: Optional[EvaluationResult] 
    refinement_count: int 
    map_html: Optional[str]
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
                print(f"!!! FLIGHT API ERROR for {origin_iata} -> {destination_iata} !!!")
                if hasattr(e, 'response') and e.response is not None:

                    print(f"Status Code: {e.response.status_code}")
                    print(f"Response Text: {e.response.text}")
                    
                else:
                    print(f"An unexpected error occurred: {e}")
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
        print(f"!!! HOTEL API ERROR for Location ID: {location_id[:30]}... !!!")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status Code: {e.response.status_code}")
            print(f"Response Text: {e.response.text}")
        else:
            print(f"An unexpected error occurred: {e}")
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



@tool
def event_finder_tool(city: str, start_date: str, end_date: str) -> List[EventInfo]:
    """
    Finds events, concerts, and attractions in a given city within a specific date range,
    sorted by relevance.
    """
    print(f"--- Calling Ticketmaster API for events in {city} ---")
    
    start_datetime = f"{start_date}T00:00:00Z"
    end_datetime = f"{end_date}T23:59:59Z"
    
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    
    params = {
        'apikey': ticketmaster_api_key,
        'city': city,
        'startDateTime': start_datetime,
        'endDateTime': end_datetime,
        'sort': 'relevance,desc', 
        'size': 50 
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get('_embedded') or not data['_embedded'].get('events'):
            print(f"-> No events found in {city} for the given dates.")
            return []

        events = []
        for event_data in data['_embedded']['events']:
            venue_info = event_data.get('_embedded', {}).get('venues', [{}])[0]
            event = EventInfo(
                name=event_data.get('name'),
                date=event_data.get('dates', {}).get('start', {}).get('localDate', ''),
                venue=venue_info.get('name', 'Venue details not available'),
                url=event_data.get('url', '#')
            )
            events.append(event)
        
        print(f"-> Found {len(events)} events.")
        return events

    except Exception as e:
        print(f"-> Ticketmaster API request or parsing failed: {e}")
        return []


@tool
def geocoding_tool(location_name: str) -> Optional[Dict[str, float]]:
    """
    Geocodes a location name (e.g., 'Rijksmuseum, Amsterdam') to its latitude and longitude.
    """
    print(f"--- Geocoding: {location_name} ---")
    try:
        geolocator = Nominatim(user_agent="ai-travel-agent")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5, return_value_on_exception=None)
        location = geocode(location_name, timeout=10)
        
        if location:
            return {"latitude": location.latitude, "longitude": location.longitude}
        return None
    except Exception as e:
        print(f"-> Geocoding failed for {location_name}: {e}")
        return None


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
    You are an expert travel agent. Your task is to select the best flight from the list below, balancing cost, convenience, and total travel time.

    **CRITICAL INSTRUCTIONS FOR LAYOVERS:**
    -   **Total travel time is paramount.** A cheap flight with an extremely long layover (e.g., more than 5 hours) is a BAD choice.
    -   Analyze the `layover_duration_minutes` for both departure and return legs.
    -   Strongly penalize any option with an excessive layover. A direct flight or one with a short layover (under 4 hours) is much more valuable than saving a small amount of money.

    **USER PREFERENCES:**
    -   Budget: €{trip_plan.budget}

    **FLIGHT OPTIONS:**
    {options_text}

    Analyze the options considering price, total flight duration, AND total layover time. Select the option that provides the most convenient and time-efficient journey for the user. Call the `FlightSelection` function with your decision.
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



def event_agent(state: TripState) -> dict:
    """Finds events and then uses an LLM to select the list based on user interests."""

    print("--- Running Smart Event Agent ---")

    trip_plan = state['trip_plan']
    if not trip_plan or not trip_plan.interests: return {"events": []}
    
    all_events = event_finder_tool.invoke({
        "city": trip_plan.destination,
        "start_date": trip_plan.start_date,
        "end_date": trip_plan.end_date,
    })
    
    if not all_events:
        return {"events": []}
    
    selected_llm = llm.bind_tools([SelectedEvents])
    
    prompt = f"""
    You are an expert event curator. Based on a user's interests, your task is to select the most relevant events from a provided list.

    User's Interests: {', '.join(trip_plan.interests)}

    Here is a list of events happening during their trip. Please review them, remove any duplicates or near-duplicates (like the same museum entry listed multiple times), and select the top 3-4 most relevant events that best match the user's interests.

    LIST OF AVAILABLE EVENTS:
    {json.dumps([event.model_dump() for event in all_events])}

    Now, call the `SelectedEvents` function with your final, selected list of events.
    """
    
    ai_message = selected_llm.invoke(prompt)
    
    if not ai_message.tool_calls:
        print("-> LLM failed to select events. Returning the raw list.")
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
    and extract all specific, physical, and geocodable places.

    **CRITICAL INSTRUCTIONS:**
    -   You MUST extract **only real, physical locations** like museums, monuments, parks, squares, famous buildings, or specific neighborhoods.
    -   You MUST **AVOID** extracting temporary items like event names, exhibitions, festivals, awards, or abstract concepts (e.g., "art-house cinema under the stars").
    -   For each extracted place, provide a `name`, `description`, `location` (city name: "{state['trip_plan'].destination}"), and a suitable `time_of_day`.

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
    Takes the list of extracted activities and enriches them with coordinates.
    """
    print("--- Running Geocoding Agent ---")
    activities = state.get("extracted_activities")
    if not activities:
        return {}

    for activity in activities:
        search_query = f"{activity.name}, {state['trip_plan'].destination}"
        coords = geocoding_tool.invoke(search_query)
        if coords:
            activity.latitude = coords['latitude']
            activity.longitude = coords['longitude']
    
    return {"extracted_activities": activities}




def activity_scheduling_agent(state: TripState) -> dict:
    """
    Takes a clean list of activities and asks the LLM to schedule them into daily plans.
    Then, it manually combines this schedule with flight and hotel info to create the final itinerary.
    """
    print("--- Running Activity Scheduling Agent ---")

    activities = state.get("extracted_activities", [])
    events = state.get("events", [])
    print(f"-> Received {len(activities)} activities and {len(events)} events to schedule.")


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


    geocoded_activities_lookup = {act.name: act for act in activities}
    
    activities_for_prompt = [
        {
            "name": act.name,
            "description": act.description,
            "location": act.location,
            "time_of_day": act.time_of_day
        }
        for act in activities
    ]


    planner_llm = llm.bind_tools([ScheduledActivities])

    prompt = f"""
    You are an expert travel planner. Your task is to organize the following list of activities into a logical daily schedule for a {trip_plan.days}-day trip.

    **Chain of Thought Process:**
    1.  First, review all the activities provided.
    2.  Second, group them logically by location or type.
    3.  Third, distribute these groups across the {trip_plan.days} days to create a sensible flow.
    4.  Fourth, ensure the final JSON output strictly adheres to the `ScheduledActivities` schema.

    **CRITICAL INSTRUCTIONS FOR A REALISTIC PLAN:**
    1.  **Group by Proximity:** Analyze the locations. Try to group activities that are geographically close to each other into the same day to minimize travel time.
    2.  **Consider Activity Scale:** Be realistic about timing. A major theme park (like Disneyland) or a day trip (like Mt. Fuji) takes a full day. Do not schedule other major activities on the same day. A museum might take half a day.
    3.  **Logical Flow:** Create a plan that flows naturally. Don't have the user zig-zagging across the city.
    4.  **Avoid Redundancy:** Do not schedule hotels (like Hotel MiraCosta) as activities.
    5.  **No Empty Days:** If you run out of activities, do not include empty days.

    **LIST OF PRE-APPROVED ACTIVITIES TO SCHEDULE:**
    {json.dumps(activities_for_prompt)}

    Now, create the most logical and efficient `ScheduledActivities` JSON object.
    """
    
    ai_message = planner_llm.invoke(prompt)
    if not ai_message.tool_calls:
        raise ValueError("LLM failed to create an activity schedule.")
        
    tool_call = ai_message.tool_calls[0]
    scheduled_activities = ScheduledActivities(**tool_call['args'])

    for day_plan in scheduled_activities.daily_plans:
        for scheduled_activity in day_plan.activities:

            original_activity = geocoded_activities_lookup.get(scheduled_activity.name)
            if original_activity:
                scheduled_activity.latitude = original_activity.latitude
                scheduled_activity.longitude = original_activity.longitude
    
    final_itinerary = Itinerary(
        selected_flight=selected_flight,
        selected_hotel=selected_hotel,
        daily_plans=scheduled_activities.daily_plans
    )
    
    print("-> Final Itinerary Assembled Successfully with Geocoded Data.")
    return {"final_itinerary": final_itinerary}
    


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

    evaluator_llm = llm.bind_tools([EvaluationResult])

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

    ai_message = evaluator_llm.invoke(prompt)
    
    if not ai_message.tool_calls:
        return {"evaluation_result": EvaluationResult(action="APPROVE", feedback="Auto-approved due to error.", total_cost=total_cost), "refinement_count": refinement_count + 1}
        
    tool_call = ai_message.tool_calls[0]
    result = EvaluationResult(**tool_call['args'])
    result.total_cost = total_cost
    
    print(f"-> Smart Decision: {result.action}. Reason: {result.feedback}")
    return {"evaluation_result": result, "refinement_count": refinement_count + 1}



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



def report_formatter_node(state: TripState) -> dict:
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
        
        if hotel.main_photo_url:
            md += f"![{hotel.hotel_name}]({hotel.main_photo_url})\n\n"
            
        md += f"### {hotel.hotel_name}\n"
        md += f"**Rating:** {hotel.rating} / 10.0 ({hotel.rating_word} based on {hotel.review_count} reviews)\n"
        md += f"**Taxes and Fees:** ~€{hotel.price_per_night:,.2f}\n" 
        md += f"**Total Price (for {num_nights} nights, {trip_plan.person} people):** €{hotel.total_price:,.2f}\n\n"
        md += "\n"

        if hotel.static_map_url:
            interactive_map_url = f"https://www.google.com/maps/search/?api=1&query={hotel.hotel_name.replace(' ', '+')}"
            
            md += f"[![Map of {hotel.hotel_name}]({hotel.static_map_url})]({interactive_map_url})\n\n"


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


        if map_html_content:
            md += "\n---\n\n## 📍 Interactive Trip Map\n"
            md += "Click on the numbered pins to see activity details.\n\n"

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

        if map_html_content:
            print(f"-> Injecting map into HTML Report (Size: {len(map_html_content)} chars)")
            html_body += f"""
            <div class="map-container">
                <h2>📍 Interactive Trip Map</h2>
                <p>Click on the numbered pins to see activity details.</p>
                {map_html_content}
            </div>
            """
        
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
workflow.add_node("geocoding_agent", geocoding_agent)
workflow.add_node("event_agent", event_agent)
workflow.add_node("data_aggregator_agent", data_aggregator_agent) 
workflow.add_node("activity_scheduling_agent", activity_scheduling_agent)
workflow.add_node("evaluator_agent", evaluator_agent)
workflow.add_node("report_formatter_node", report_formatter_node) 
workflow.add_node("map_generator_node", map_generator_node)


workflow.add_edge(START, "planner_agent")

workflow.add_edge("planner_agent", "flight_agent")
workflow.add_edge("planner_agent", "hotel_agent")
workflow.add_edge("planner_agent", "event_agent")

workflow.add_edge("flight_agent", "data_aggregator_agent")
workflow.add_edge("hotel_agent", "data_aggregator_agent")
workflow.add_edge("event_agent", "data_aggregator_agent")

workflow.add_edge("data_aggregator_agent", "activity_extraction_agent")

workflow.add_edge("activity_extraction_agent", "geocoding_agent")

workflow.add_edge("geocoding_agent", "activity_scheduling_agent")


workflow.add_edge("activity_scheduling_agent", "evaluator_agent")

workflow.add_conditional_edges(
    "evaluator_agent",
    should_refine_or_end,
    {
        "refine_hotel": "hotel_agent",           
        "refine_flight": "flight_agent",         
        "end": "map_generator_node"           
    }
)


workflow.add_edge("map_generator_node", "report_formatter_node")
workflow.add_edge("report_formatter_node", END)


app = workflow.compile()



