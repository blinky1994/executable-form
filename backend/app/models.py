from typing import Any, Literal

from pydantic import BaseModel, Field


FieldType = Literal["text", "number", "select", "checkbox", "date", "file"]


class FieldOption(BaseModel):
    value: str
    label: str


class FormField(BaseModel):
    id: str
    type: FieldType
    label: str
    section: str | None = None
    visible: bool = True
    required: bool = False
    disabled: bool = False
    loading: bool = False
    value: Any = None
    options: list[FieldOption] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AsyncRequest(BaseModel):
    id: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class AsyncResult(BaseModel):
    id: str
    result: Any


class EvaluationRequest(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    async_results: dict[str, Any] = Field(default_factory=dict)


class FormOutput(BaseModel):
    version: str
    fields: list[FormField]
    async_requests: list[AsyncRequest] = Field(default_factory=list)
    form_errors: list[str] = Field(default_factory=list)
    can_submit: bool = False
