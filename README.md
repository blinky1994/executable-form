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

## 3. Comparison With JSON Schema Driven Forms

JSON Schema driven forms are the common approach for dynamic forms. The backend returns a declarative schema, and the frontend uses a renderer such as RJSF or a custom component registry to build the UI.

That approach is excellent when the form is mostly structural:

- field names
- field types
- required fields
- primitive validation
- nested object/array shape
- enum options
- simple defaults

Executable forms target a different pain point: forms where the hard part is not shape, but behavior.

### High-Level Difference

| Dimension | JSON Schema Driven Form | Executable Form |
| --- | --- | --- |
| Primary abstraction | Data schema/config | Function evaluation |
| Backend output | Static or semi-static schema | Current render model for current state |
| Business logic | Encoded as schema keywords, custom DSL, or frontend callbacks | Written directly in Python |
| Conditional visibility | Usually custom `uiSchema`, `if/then/else`, or renderer-specific rules | Normal `if` statements |
| Cross-field validation | Awkward; often needs custom validators | Direct references to any state value |
| Async dependencies | Usually outside JSON Schema; added through frontend glue | Evaluator emits explicit async requests |
| Computed fields | Usually custom extension | Direct Python computation |
| Debugging | Inspect schema plus renderer behavior | Step through a function |
| Tests | Schema snapshots plus frontend tests | Unit tests against evaluator output |
| Frontend role | Schema interpreter and behavior coordinator | Generic renderer and host runtime |
| Best fit | CRUD/forms with predictable shape | Workflow-like enterprise forms with branching rules |

### Typical JSON Schema Flow

```text
Backend returns schema
  -> Frontend renderer parses schema
  -> Frontend applies UI schema/extensions
  -> Frontend wires custom behavior
  -> Frontend submits data
  -> Backend validates again
```

Example:

```json
{
  "type": "object",
  "properties": {
    "resource_type": {
      "type": "string",
      "enum": ["s3_bucket", "security_group", "iam_role"]
    },
    "cidr": {
      "type": "string"
    }
  },
  "required": ["resource_type"]
}
```

This describes the data shape well. It does not naturally express:

- show `cidr` only when `resource_type == "security_group"`
- validate CIDR using real IP parsing
- reject public SSH/RDP/database ports
- request AWS regions only when the selected resource needs a region
- keep a loading state while region metadata is unresolved
- compute `can_submit` from visible required fields plus async status

Those behaviors normally move into:

- custom JSON Schema keywords
- `uiSchema`
- frontend `useEffect`
- frontend validators
- a homegrown rule DSL
- backend revalidation after submit

At that point the "schema driven" form has quietly become a distributed behavior engine.

### Executable Form Flow

```text
Frontend sends current state
  -> Backend evaluator runs normal Python
  -> Backend returns FormOutput
  -> Frontend renders fields exactly as described
  -> Frontend resolves emitted async requests generically
  -> Backend remains source of truth
```

Example:

```python
is_security_group = resource_type == "security_group"
port = state.get("port")
cidr = state.get("cidr", "")

cidr_errors = validate_cidr(cidr) if is_security_group else []
if is_security_group and port in DANGEROUS_PUBLIC_PORTS and is_public_cidr(cidr):
    cidr_errors.append(f"{DANGEROUS_PUBLIC_PORTS[port]} cannot be open to the public internet.")

fields.append(text_field(
    id="cidr",
    label="Allowed CIDR",
    visible=is_security_group,
    required=is_security_group,
    value=cidr,
    errors=cidr_errors,
))
```

The dependency chain is not encoded into a separate rule format. It is the execution order of the function:

```text
read state -> derive facts -> append fields -> collect errors -> return output
```

### Where JSON Schema Still Wins

JSON Schema is still a good choice when:

- forms closely match API payload shape
- rules are mostly type/required/min/max/pattern/enum
- product teams need broad ecosystem compatibility
- forms are authored by config rather than engineers
- runtime behavior must be inspectable as static data
- offline schema validation is enough

For simple forms, executable forms are overkill.

### Where Executable Forms Win

Executable forms are better when:

- business rules are already written or reviewed by backend/domain engineers
- fields branch into different workflows
- visibility and validation depend on several other fields
- async lookups affect later fields
- computed values need normal programming constructs
- compliance wants deterministic, testable rules
- frontend teams should not translate backend rules by hand

The key tradeoff:

```text
JSON Schema optimizes for portable structure.
Executable Forms optimize for executable behavior.
```

### Concrete AWS Compliance Example

The current prototype includes rules that are awkward in plain JSON Schema:

- S3 bucket naming rules using regex plus IP-address rejection.
- S3 encryption policy changes by check level.
- Security group port range validation.
- CIDR parsing through Python's `ipaddress` module.
- Public internet checks for SSH, RDP, MySQL, PostgreSQL, Redis, and Elasticsearch.
- IAM role name validation.
- Dynamic AWS region lookup emitted as an async request.

With JSON Schema, these would likely become a mix of `pattern`, custom validation code, and frontend orchestration. Here they live in one Python evaluator and are covered by pytest.

## 4. Goals

- Let backend/domain engineers author form behavior in Python using normal language control flow.
- Keep frontend rendering generic and predictable.
- Make form rules unit-testable with pytest.
- Support nested conditionals, dependency chains, cross-field validation, computed fields, and async lookup coordination.
- Prove the paradigm over HTTP before investing in WASM.
- Keep legacy forms isolated instead of forcing backward compatibility into the new model.

## 5. Non-Goals

- Do not build a visual low-code form builder.
- Do not replace TanStack Form immediately.
- Do not support every legacy form shape in the first abstraction.
- Do not compile to WASM in the first milestone.
- Do not expose arbitrary Python execution from user-authored input.
- Do not attempt full offline support until the runtime model is proven.

## 6. Core Architecture

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

## 7. Form Contract

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

## 8. Python Authoring Model

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

## 9. Async Boundary

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

## 10. Frontend FormRunner

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

## 11. API Design

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

## 12. Legacy Strategy

Legacy forms should not shape the new abstraction.

- Existing forms stay as they are.
- Legacy receives bug fixes only.
- New forms use executable forms.
- A legacy form migrates only when it needs meaningful feature work.
- No universal adapter for old form config in milestone one.

This is a strangler pattern, not a big-bang rewrite.

## 13. Runtime Roadmap

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

## 14. Key Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Python evaluator becomes unstructured business spaghetti | Hard to maintain | Provide helper constructors, tests, linting, examples, and review guidelines |
| HTTP evaluation feels too slow | Bad UX | Debounce, cancel stale requests, optimize evaluator, later move to WASM |
| Async behavior becomes nondeterministic | Flaky UI | Model async as explicit requests/results |
| Frontend needs escape hatches | Logic leaks back into React | Permit UI-only hooks, reject domain-rule hooks |
| WASM bundle is too large | Slow startup | Treat WASM as milestone 4, not the initial proof |
| Business logic exposed client-side | Compliance concern | Do not claim WASM is secure obfuscation; use server runtime for sensitive rules |
| Legacy migration expands scope | Project stalls | Use strangler migration triggers |

## 15. Security Notes

WASM is not a security boundary. Client-side logic can be inspected, copied, and manipulated.

Authoritative submission validation must still run on the server. Executable forms improve authoring and UX consistency; they do not replace backend enforcement.

Sensitive eligibility rules, pricing rules, fraud checks, and entitlement checks should either:

- stay server-side, or
- run client-side only as previews and be revalidated on submit.

## 16. Testing Strategy

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

## 17. First Prototype Task List

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

## 18. Prototype Decisions

| Question | Decision |
| --- | --- |
| First real form domain | AWS compliance configuration checks |
| Credible demo fields | AWS resource selection and resource-specific config checks |
| Section/layout metadata in milestone one | No |
| Hidden field submit behavior | Strip hidden fields from submitted payloads |
| File input representation | Represent unresolved file/resource state as loading state |
| Client-side-safe WASM rules | TODO |
| TanStack Query integration | Try it if it keeps async request handling simpler |

## 19. Recommended Starting Point

Start with the HTTP prototype. Do not start with WASM.

The first deliverable should answer one narrow question:

> Can a backend-authored Python function express a complex form more clearly than frontend form logic?

If yes, harden the contract. If no, stop before building a runtime around a weak authoring model.
