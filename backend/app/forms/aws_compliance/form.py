import ipaddress
import re
from typing import Any

from app.models import AsyncRequest, AsyncResult, FieldOption, FormField, FormOutput

AWS_REGIONS = [
    "ap-southeast-1",
    "ap-southeast-2",
    "us-east-1",
    "us-west-2",
    "eu-west-1",
]

DANGEROUS_PUBLIC_PORTS = {
    22: "SSH",
    3389: "RDP",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    9200: "Elasticsearch",
}

BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
ROLE_NAME_PATTERN = re.compile(r"^[\w+=,.@-]{1,64}$")


def option(value: str, label: str | None = None) -> FieldOption:
    return FieldOption(value=value, label=label or value)


def select_field(
    *,
    id: str,
    label: str,
    value: Any = None,
    options: list[FieldOption] | None = None,
    visible: bool = True,
    required: bool = False,
    disabled: bool = False,
    loading: bool = False,
    errors: list[str] | None = None,
) -> FormField:
    return FormField(
        id=id,
        type="select",
        label=label,
        value=value,
        visible=visible,
        required=required,
        disabled=disabled,
        loading=loading,
        options=options or [],
        errors=errors or [],
    )


def text_field(
    *,
    id: str,
    label: str,
    value: Any = "",
    visible: bool = True,
    required: bool = False,
    disabled: bool = False,
    errors: list[str] | None = None,
) -> FormField:
    return FormField(
        id=id,
        type="text",
        label=label,
        value=value,
        visible=visible,
        required=required,
        disabled=disabled,
        errors=errors or [],
    )


def number_field(
    *,
    id: str,
    label: str,
    value: Any = None,
    visible: bool = True,
    required: bool = False,
    disabled: bool = False,
    errors: list[str] | None = None,
) -> FormField:
    return FormField(
        id=id,
        type="number",
        label=label,
        value=value,
        visible=visible,
        required=required,
        disabled=disabled,
        errors=errors or [],
    )


def checkbox_field(
    *,
    id: str,
    label: str,
    value: bool = False,
    visible: bool = True,
    required: bool = False,
    disabled: bool = False,
    errors: list[str] | None = None,
) -> FormField:
    return FormField(
        id=id,
        type="checkbox",
        label=label,
        value=value,
        visible=visible,
        required=required,
        disabled=disabled,
        errors=errors or [],
    )


def required_visible_fields_present(
    fields: list[FormField], state: dict[str, Any]
) -> bool:
    for field in fields:
        if not field.visible or not field.required:
            continue
        value = state.get(field.id, field.value)
        if value is None or value == "":
            return False
    return True


def strip_hidden_fields(
    fields: list[FormField], state: dict[str, Any]
) -> dict[str, Any]:
    return {
        field.id: state.get(field.id, field.value)
        for field in fields
        if field.visible
    }


def resolve_async_request(request: AsyncRequest) -> AsyncResult:
    if request.type == "aws_regions_lookup":
        return AsyncResult(id=request.id, result=AWS_REGIONS)

    raise ValueError(f"Unsupported async request type: {request.type}")


def validate_bucket_name(bucket_name: str) -> list[str]:
    if not bucket_name:
        return []

    errors = []
    if not BUCKET_NAME_PATTERN.match(bucket_name):
        errors.append(
            "Bucket name must be 3-63 chars, lowercase letters, numbers, dots, or hyphens."
        )
    if ".." in bucket_name or ".-" in bucket_name or "-." in bucket_name:
        errors.append("Bucket name cannot contain adjacent dots or dot-hyphen pairs.")
    try:
        ipaddress.ip_address(bucket_name)
        errors.append("Bucket name cannot be formatted like an IP address.")
    except ValueError:
        pass
    return errors


def validate_port(port: Any) -> list[str]:
    if port in (None, ""):
        return []
    if not isinstance(port, int):
        return ["Port must be a whole number."]
    if port < 1 or port > 65535:
        return ["Port must be between 1 and 65535."]
    return []


def validate_cidr(cidr: str) -> list[str]:
    if not cidr:
        return []
    try:
        ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return ["CIDR must be a valid IPv4 or IPv6 network, for example 10.0.0.0/24."]
    return []


def is_public_cidr(cidr: str) -> bool:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    return network.prefixlen == 0


def validate_role_name(role_name: str) -> list[str]:
    if not role_name:
        return []
    if not ROLE_NAME_PATTERN.match(role_name):
        return [
            "Role name must be 1-64 chars and use only letters, numbers, or +=,.@-_ characters."
        ]
    return []


def evaluate(
    state: dict[str, Any],
    context: dict[str, Any] | None = None,
    async_results: dict[str, Any] | None = None,
) -> FormOutput:
    context = context or {}
    async_results = async_results or {}
    fields: list[FormField] = []
    async_requests: list[AsyncRequest] = []

    resource_type = state.get("resource_type")
    check_level = state.get("check_level", "baseline")

    fields.append(
        select_field(
            id="resource_type",
            label="AWS Resource Type",
            value=resource_type,
            required=True,
            options=[
                option("s3_bucket", "S3 Bucket"),
                option("security_group", "Security Group"),
                option("iam_role", "IAM Role"),
            ],
        )
    )

    fields.append(
        select_field(
            id="check_level",
            label="Check Level",
            value=check_level,
            required=True,
            options=[
                option("baseline", "Baseline"),
                option("cis", "CIS"),
                option("internal", "Internal Policy"),
            ],
        )
    )

    is_s3 = resource_type == "s3_bucket"
    is_security_group = resource_type == "security_group"
    is_iam_role = resource_type == "iam_role"
    requires_region = is_s3 or is_security_group
    region_options = async_results.get("aws_regions")

    if requires_region and region_options is None:
        async_requests.append(
            AsyncRequest(
                id="aws_regions",
                type="aws_regions_lookup",
                params={
                    "provider": "aws",
                    "partition": context.get("partition", "aws"),
                },
            )
        )

    fields.append(
        select_field(
            id="region",
            label="Region",
            value=state.get("region"),
            visible=requires_region,
            required=requires_region,
            loading=requires_region and region_options is None,
            options=[option(region) for region in (region_options or [])],
        )
    )

    bucket_name = state.get("bucket_name", "")
    fields.append(
        text_field(
            id="bucket_name",
            label="Bucket Name",
            value=bucket_name,
            visible=is_s3,
            required=is_s3,
            errors=validate_bucket_name(bucket_name) if is_s3 else [],
        )
    )

    public_access = bool(state.get("public_access"))
    fields.append(
        checkbox_field(
            id="public_access",
            label="Allow Public Access",
            value=public_access,
            visible=is_s3,
            errors=(
                ["Public S3 access is not allowed for baseline checks."]
                if is_s3 and check_level in {"baseline", "cis"} and public_access
                else []
            ),
        )
    )

    encryption = state.get("encryption")
    encryption_errors = []
    if is_s3 and check_level in {"baseline", "cis"} and encryption == "none":
        encryption_errors.append("S3 buckets must enable default encryption.")
    if is_s3 and check_level == "internal" and encryption != "sse-kms":
        encryption_errors.append("Internal policy requires SSE-KMS encryption.")

    fields.append(
        select_field(
            id="encryption",
            label="Default Encryption",
            value=encryption,
            visible=is_s3,
            required=is_s3,
            options=[
                option("none", "None"),
                option("sse-s3", "SSE-S3"),
                option("sse-kms", "SSE-KMS"),
            ],
            errors=encryption_errors,
        )
    )

    port = state.get("port")
    cidr = state.get("cidr", "")
    port_errors = validate_port(port) if is_security_group else []
    cidr_errors = validate_cidr(cidr) if is_security_group else []
    if (
        is_security_group
        and isinstance(port, int)
        and port in DANGEROUS_PUBLIC_PORTS
        and is_public_cidr(cidr)
    ):
        cidr_errors.append(
            f"{DANGEROUS_PUBLIC_PORTS[port]} cannot be open to the public internet."
        )

    fields.append(
        number_field(
            id="port",
            label="Inbound Port",
            value=port,
            visible=is_security_group,
            required=is_security_group,
            errors=port_errors,
        )
    )

    fields.append(
        text_field(
            id="cidr",
            label="Allowed CIDR",
            value=cidr,
            visible=is_security_group,
            required=is_security_group,
            errors=cidr_errors,
        )
    )

    role_name = state.get("role_name", "")
    fields.append(
        text_field(
            id="role_name",
            label="Role Name",
            value=role_name,
            visible=is_iam_role,
            required=is_iam_role,
            errors=validate_role_name(role_name) if is_iam_role else [],
        )
    )

    admin_policy = bool(state.get("admin_policy"))
    fields.append(
        checkbox_field(
            id="admin_policy",
            label="Attach AdministratorAccess",
            value=admin_policy,
            visible=is_iam_role,
            errors=(
                ["AdministratorAccess requires internal policy exception approval."]
                if is_iam_role and admin_policy and check_level == "internal"
                else []
            ),
        )
    )

    all_errors = [error for field in fields for error in field.errors]
    return FormOutput(
        version="aws-compliance-v1",
        fields=fields,
        async_requests=async_requests,
        form_errors=[],
        can_submit=(
            len(all_errors) == 0
            and len(async_requests) == 0
            and required_visible_fields_present(fields, state)
        ),
    )
