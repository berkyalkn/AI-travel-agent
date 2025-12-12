from typing_extensions import TypedDict
from typing import Optional, List
from schemas import (
    TripRequest, FlightInfo, HotelInfo, Activity, EventInfo, 
    Itinerary, EvaluationResult
)

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