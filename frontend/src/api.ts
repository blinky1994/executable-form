import type { AsyncRequest, AsyncResult, EvaluationRequest, FormOutput } from './types';

export async function evaluateForm(
  formId: string,
  payload: EvaluationRequest,
  signal?: AbortSignal,
): Promise<FormOutput> {
  const response = await fetch(`/api/forms/${formId}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Evaluation failed with ${response.status}`);
  }

  return response.json();
}

export async function resolveAsyncRequest(
  formId: string,
  request: AsyncRequest,
  signal?: AbortSignal,
): Promise<AsyncResult> {
  const response = await fetch(`/api/forms/${formId}/async-requests/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Async request failed with ${response.status}`);
  }

  return response.json();
}
