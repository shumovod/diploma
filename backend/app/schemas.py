from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    title: str
    url: str
    favicon_url: str = Field(default="")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    text: str
    sources: list[SourceItem] = Field(default_factory=list)
    source_type: str
