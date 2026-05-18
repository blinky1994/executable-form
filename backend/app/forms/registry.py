from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.forms import aws_compliance
from app.models import AsyncRequest, AsyncResult, FormOutput

EvaluateFn = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], FormOutput]
ResolveAsyncFn = Callable[[AsyncRequest], AsyncResult]


@dataclass(frozen=True)
class FormDefinition:
    id: str
    evaluate: EvaluateFn
    resolve_async_request: ResolveAsyncFn


FORMS: dict[str, FormDefinition] = {
    "aws-compliance": FormDefinition(
        id="aws-compliance",
        evaluate=aws_compliance.evaluate,
        resolve_async_request=aws_compliance.resolve_async_request,
    )
}


def get_form(form_id: str) -> FormDefinition | None:
    return FORMS.get(form_id)
