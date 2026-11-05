from pydantic import BaseModel

class ToolStep(BaseModel):
    name: str
    arguments: dict
    result: str

class AgentResult(BaseModel):
    answer: str
    steps: list[ToolStep]
    sources: list[str] = []
    unsupported: list[float] = []

