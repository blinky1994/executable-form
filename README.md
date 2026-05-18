# Executable Forms Technical Design

## Quickstart

Install dependencies:

```powershell
python -m uv sync
cd frontend
corepack pnpm install
```

Run the backend:

```powershell
cd backend
python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Run the frontend in another terminal:

```powershell
cd frontend
corepack pnpm run dev
```

Open the app:

```text
http://127.0.0.1:5173
```

Useful checks:

```powershell
python -m uv run pytest
cd frontend
corepack pnpm run build
```

## 1. Problem

Complex enterprise forms are not just collections of inputs. They contain conditional visibility, cross-field validation, derived values, async lookups, branching workflows, and legacy migration pressure.

The current frontend-heavy model makes React responsible for translating business rules into UI behavior. That creates duplicated logic, slow requirement handoffs, inconsistent validation, and high regression risk as forms scale.

## 2. Thesis

An executable form is a pure backend-authored function:

```python
evaluate_form(state) -> FormOutput
```

The function receives the current form state and returns the complete render model:

- visible fields
- labels and input types
- required and disabled flags
- field options
- validation errors
- computed values
- submit eligibility
- async lookup requests, if any

React does not own business logic. React owns rendering, input ergonomics, accessibility, styling, and interaction quality.

## 3. Goals

- Let backend/domain engineers author form behavior in Python using normal language control flow.
- Keep frontend rendering generic and predictable.
- Make form rules unit-testable with pytest.
- Support nested conditionals, dependency chains, cross-field validation, computed fields, and async lookup coordination.
- Prove the paradigm over HTTP before investing in WASM.
- Keep legacy forms isolated instead of forcing backward compatibility into the new model.

## 4. Non-Goals

- Do not build a visual low-code form builder.
- Do not replace TanStack Form immediately.
- Do not support every legacy form shape in the first abstraction.
- Do not compile to WASM in the first milestone.
- Do not expose arbitrary Python execution from user-authored input.
- Do not attempt full offline support until the runtime model is proven.

## 5. Core Architecture

```text
Browser
  React FormRunner
    - owns rendering
    - owns local input state
    - debounces evaluation calls
    - renders returned fields
    - displays returned errors

API
  POST /forms/{form_id}/evaluate
    - receives state
    - loads registered form evaluator
    - returns FormOutput

Form Engine
  Python evaluator functions
    - encode business rules
    - compute visibility
    - compute validations
    - compute derived values
    - emit async lookup requests
```

Initial runtime:

```text
User input -> React state -> debounced HTTP evaluate -> Python function -> FormOutput -> React render
```

Future runtime:

```text
User input -> React state -> local WASM evaluate -> FormOutput -> React render
```

## 6. Form Contract

### Evaluation Input

```json
{
  "state": {
    "cloud_provider": "aws",
    "resource_type": "s3_bucket",
    "check_level": "baseline"
  },
  "context": {
    "user_id": "u_123",
    "locale": "en-SG",
    "feature_flags": []
  },
  "async_results": {
    "aws_regions": ["ap-southeast-1", "us-east-1"]
  }
}
```

### Evaluation Output

```json
{
  "version": "aws-compliance-v1",
  "fields": [
    {
      "id": "resource_type",
      "type": "select",
      "label": "AWS Resource Type",
      "visible": true,
      "required": true,
      "disabled": false,
      "value": "s3_bucket",
      "options": [
        { "value": "s3_bucket", "label": "S3 Bucket" },
        { "value": "security_group", "label": "Security Group" },
        { "value": "iam_role", "label": "IAM Role" }
      ],
      "errors": []
    }
  ],
  "async_requests": [],
  "form_errors": [],
  "can_submit": true
}
```

## 7. Python Authoring Model

The backend author writes ordinary Python. Execution order is the dependency model.

```python
def evaluate(state: dict, context: dict, async_results: dict) -> dict:
    fields = []

    resource_type = state.get("resource_type")

    fields.append(select_field(
        id="resource_type",
        label="AWS Resource Type",
        required=True,
        value=resource_type,
        options=[
            {"value": "s3_bucket", "label": "S3 Bucket"},
            {"value": "security_group", "label": "Security Group"},
            {"value": "iam_role", "label": "IAM Role"},
        ],
    ))

    check_level = state.get("check_level")
    fields.append(select_field(
        id="check_level",
        label="Check Level",
        required=True,
        value=check_level,
        options=[
            {"value": "baseline", "label": "Baseline"},
            {"value": "cis", "label": "CIS"},
            {"value": "internal", "label": "Internal Policy"},
        ],
    ))

    is_s3 = resource_type == "s3_bucket"
    is_security_group = resource_type == "security_group"
    requires_region = resource_type in {"s3_bucket", "security_group"}
    region = state.get("region")

    async_requests = []
    if requires_region and "aws_regions" not in async_results:
        async_requests.append({
            "id": "aws_regions",
            "type": "aws_regions_lookup",
            "params": {"provider": "aws"},
        })

    fields.append(select_field(
        id="region",
        label="Region",
        visible=requires_region,
        required=requires_region,
        value=region,
        loading=requires_region and "aws_regions" not in async_results,
        options=[
            {"value": item, "label": item}
            for item in async_results.get("aws_regions", [])
        ],
    ))

    public_access = bool(state.get("public_access"))
    fields.append(checkbox_field(
        id="public_access",
        label="Allow Public Access",
        visible=is_s3,
        value=public_access,
        errors=["Public S3 access is not allowed for baseline checks"]
        if is_s3 and check_level == "baseline" and public_access
        else [],
    ))

    cidr = state.get("cidr", "")
    fields.append(text_field(
        id="cidr",
        label="Allowed CIDR",
        visible=is_security_group,
        required=is_security_group,
        value=cidr,
        errors=["0.0.0.0/0 is not allowed for SSH"]
        if is_security_group and state.get("port") == 22 and cidr == "0.0.0.0/0"
        else [],
    ))

    errors = [error for field in fields for error in field.get("errors", [])]

    return {
        "version": "aws-compliance-v1",
        "fields": fields,
        "async_requests": async_requests,
        "form_errors": [],
        "can_submit": len(errors) == 0 and required_visible_fields_present(fields, state),
    }
```

## 8. Async Boundary

WASM and pure evaluators should not perform network calls directly. Async is modeled as a host interaction:

1. Evaluator detects missing external data.
2. Evaluator emits an `async_request`.
3. React host performs the request through normal API/query tooling.
4. Result is passed back into the next evaluation under `async_results`.

Example:

```json
{
  "async_requests": [
    {
      "id": "customer_tier",
      "type": "customer_tier_lookup",
      "params": { "customer_id": "c_123" }
    }
  ]
}
```

This keeps form evaluation deterministic and testable.

## 9. Frontend FormRunner

Frontend responsibilities:

- Keep local form values.
- Call evaluator on value changes with debounce.
- Render field types through a component registry.
- Apply returned `visible`, `disabled`, `required`, `errors`, `value`, and `options`.
- Execute async requests and feed results into future evaluations.
- Strip hidden field values from the submitted payload.
- Submit final state to the product API.

Field component registry:

```ts
const FIELD_COMPONENTS = {
  text: TextField,
  number: NumberField,
  select: SelectField,
  checkbox: CheckboxField,
  date: DateField,
  file: FileField,
};
```

TanStack Form can remain the local input/state layer. It should not encode domain rules.

## 10. API Design

```http
POST /forms/{form_id}/evaluate
Content-Type: application/json
```

Request:

```json
{
  "state": {},
  "context": {},
  "async_results": {}
}
```

Response:

```json
{
  "version": "form-version",
  "fields": [],
  "async_requests": [],
  "form_errors": [],
  "can_submit": false
}
```

Implementation sketch:

```python
@app.post("/forms/{form_id}/evaluate")
def evaluate_form(form_id: str, request: EvaluationRequest) -> FormOutput:
    evaluator = registry.get(form_id)
    return evaluator(request.state, request.context, request.async_results)
```

## 11. Legacy Strategy

Legacy forms should not shape the new abstraction.

- Existing forms stay as they are.
- Legacy receives bug fixes only.
- New forms use executable forms.
- A legacy form migrates only when it needs meaningful feature work.
- No universal adapter for old form config in milestone one.

This is a strangler pattern, not a big-bang rewrite.

## 12. Runtime Roadmap

### Milestone 1: HTTP Prototype

Purpose: prove authoring experience.

- Build one real-ish AWS compliance form evaluator in Python.
- Expose `POST /forms/{form_id}/evaluate`.
- Render it with React and TanStack Form.
- Add one nested conditional.
- Add one dependency chain.
- Add one cross-field validation.
- Add one async request placeholder.
- Represent resource/config loading through field-level `loading` state.
- Write pytest coverage for evaluator behavior.

Success question:

> Does writing the form logic in Python feel clearer than writing it in React?

### Milestone 2: Form Contract Hardening

Purpose: make the shape reliable.

- Add Pydantic models for `Field`, `FormOutput`, `AsyncRequest`.
- Add frontend TypeScript types generated from the contract.
- Add field registry and unsupported-field handling.
- Add field ordering and grouping.
- Add deterministic evaluator tests.
- Add contract snapshot tests.

### Milestone 3: Production HTTP Runtime

Purpose: make the server evaluation path usable for internal forms.

- Debounce and cancel stale evaluations.
- Add request sequence IDs to prevent out-of-order UI updates.
- Add server-side caching for stable lookups.
- Add auth and context injection.
- Add observability for evaluation latency and error rate.
- Add rate limits.

### Milestone 4: WASM Experiment

Purpose: remove per-keystroke network dependency.

- Evaluate Pyodide bundle size and startup latency.
- Run the same Python evaluator locally in browser.
- Compare HTTP vs Pyodide latency on real form interactions.
- Verify Python-to-JS serialization costs.
- Keep async as host-provided requests/results.

### Milestone 5: Portable Runtime

Purpose: decide whether this becomes a broader platform primitive.

- If Pyodide is too heavy, test a small Rust evaluator runtime.
- Keep Python authoring only if translation/compilation is practical.
- Define runtime package boundaries.
- Explore React/Vue/Angular adapters only after React implementation works.

## 13. Key Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Python evaluator becomes unstructured business spaghetti | Hard to maintain | Provide helper constructors, tests, linting, examples, and review guidelines |
| HTTP evaluation feels too slow | Bad UX | Debounce, cancel stale requests, optimize evaluator, later move to WASM |
| Async behavior becomes nondeterministic | Flaky UI | Model async as explicit requests/results |
| Frontend needs escape hatches | Logic leaks back into React | Permit UI-only hooks, reject domain-rule hooks |
| WASM bundle is too large | Slow startup | Treat WASM as milestone 4, not the initial proof |
| Business logic exposed client-side | Compliance concern | Do not claim WASM is secure obfuscation; use server runtime for sensitive rules |
| Legacy migration expands scope | Project stalls | Use strangler migration triggers |

## 14. Security Notes

WASM is not a security boundary. Client-side logic can be inspected, copied, and manipulated.

Authoritative submission validation must still run on the server. Executable forms improve authoring and UX consistency; they do not replace backend enforcement.

Sensitive eligibility rules, pricing rules, fraud checks, and entitlement checks should either:

- stay server-side, or
- run client-side only as previews and be revalidated on submit.

## 15. Testing Strategy

Evaluator tests:

- Initial state returns only top-level fields.
- Selecting AWS resource type reveals the correct branch.
- Nested branch reveals correct child fields.
- Cross-field validation emits expected errors.
- Computed fields update from dependencies.
- Required visible empty fields block submit.
- Hidden required fields do not block submit.
- Hidden fields are stripped from submit payloads.
- Async request is emitted when external data is missing.
- Async result changes subsequent output.
- Loading state is shown while resource metadata is unresolved.

Frontend tests:

- Renders returned visible fields.
- Does not render hidden fields.
- Displays field errors.
- Applies disabled and required flags.
- Ignores stale evaluate responses.
- Executes async request once per stable key.

## 16. First Prototype Task List

1. Create `form_engine/aws_compliance.py`.
2. Define simple field helper functions.
3. Implement `evaluate(state, context, async_results)`.
4. Add FastAPI `POST /forms/aws-compliance/evaluate`.
5. Build React `FormRunner`.
6. Add field components for text, number, select, checkbox, and date.
7. Add debounced evaluation.
8. Add AWS resource selection for S3 buckets, security groups, and IAM roles.
9. Add one nested conditional based on selected resource type and check level.
10. Add one dependency chain for resource type -> region lookup -> resource-specific config checks.
11. Add one cross-field validation, such as SSH port plus `0.0.0.0/0`.
12. Strip hidden fields from the final submit payload.
13. Add field-level loading state for unresolved resource metadata.
14. Try TanStack Query for async request execution if it stays simple.
15. Add pytest coverage for evaluator output.
16. Record whether the authoring model feels better than React logic.

## 17. Prototype Decisions

| Question | Decision |
| --- | --- |
| First real form domain | AWS compliance configuration checks |
| Credible demo fields | AWS resource selection and resource-specific config checks |
| Section/layout metadata in milestone one | No |
| Hidden field submit behavior | Strip hidden fields from submitted payloads |
| File input representation | Represent unresolved file/resource state as loading state |
| Client-side-safe WASM rules | TODO |
| TanStack Query integration | Try it if it keeps async request handling simpler |

## 18. Recommended Starting Point

Start with the HTTP prototype. Do not start with WASM.

The first deliverable should answer one narrow question:

> Can a backend-authored Python function express a complex form more clearly than frontend form logic?

If yes, harden the contract. If no, stop before building a runtime around a weak authoring model.
