from pydantic import BaseModel, Field

from app.core.constants import EntityType


class EntityCreate(BaseModel):
    type: EntityType
    value: str = Field(min_length=2, max_length=2000)


class EntityResponse(BaseModel):
    id: str
    type: EntityType
    raw_value: str
    normalized_value: str
    display_value: str

