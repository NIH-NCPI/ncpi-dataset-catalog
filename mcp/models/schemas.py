from pydantic import BaseModel


class DatasetHit(BaseModel):
    name: str
    description: str
    distance: float
