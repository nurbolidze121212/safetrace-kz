from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import MAX_MATERIALS, MAX_TEXT

Mode = Literal["local", "cloud", "synthetic", "replay"]


class MaterialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(default="", max_length=MAX_TEXT)
    url: str = Field(default="", max_length=2048)
    source: str = Field(default="Не указан", max_length=160)
    published_at: datetime | None = None
    image_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}\.(png|jpg|webp)$")

    @field_validator("url")
    @classmethod
    def safe_url_shape(cls, value):
        if value:
            from .links import validate_url

            validate_url(value)
        return value

    @field_validator("published_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Время публикации должно содержать часовой пояс.")
        return value

    @model_validator(mode="after")
    def nonempty(self):
        if not (self.text.strip() or self.url.strip() or self.image_id):
            raise ValueError("Добавьте текст, URL или изображение.")
        return self


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=180)
    mode: Mode = "local"
    materials: list[MaterialInput] = Field(min_length=1, max_length=MAX_MATERIALS)


class DecisionInput(BaseModel):
    decision: Literal["confirmed", "false_positive", "needs_data"]
    comment: str = Field(default="", max_length=2000)


class Claim(BaseModel):
    kind: Literal[
        "call_to_action", "gambling", "bonus", "promise", "warning", "news", "education", "free_game"
    ]
    quote: str = Field(min_length=1, max_length=500)
    source_id: str = Field(max_length=100)
    explanation: str = Field(max_length=800)


class ContextExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["ru", "kk", "mixed", "other"]
    context: Literal["promotion", "warning", "news", "education", "free_game", "affiliate", "ambiguous"]
    claims: list[Claim] = Field(max_length=30)
    contradictions: list[str] = Field(max_length=10)
    limitations: list[str] = Field(max_length=10)
