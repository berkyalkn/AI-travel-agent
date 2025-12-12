from typing import List
from pydantic import BaseModel

class ActivitySearchRequest(BaseModel):
    destination: str
    interests: List[str]