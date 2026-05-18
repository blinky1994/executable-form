from app.forms.aws_compliance.form import evaluate, resolve_async_request, strip_hidden_fields
from app.models import AsyncRequest


def field_by_id(output, field_id):
    return next(field for field in output.fields if field.id == field_id)


def test_initial_state_returns_top_level_fields_only():
    output = evaluate({}, {}, {})

    assert field_by_id(output, "resource_type").visible is True
    assert field_by_id(output, "check_level").visible is True
    assert field_by_id(output, "region").visible is False
    assert output.can_submit is False


def test_s3_emits_region_lookup_and_loading_state():
    output = evaluate({"resource_type": "s3_bucket"}, {}, {})

    assert output.async_requests[0].id == "aws_regions"
    assert field_by_id(output, "region").loading is True
    assert output.can_submit is False


def test_s3_region_options_use_async_result():
    output = evaluate(
        {"resource_type": "s3_bucket", "region": "ap-southeast-1"},
        {},
        {"aws_regions": ["ap-southeast-1"]},
    )

    region = field_by_id(output, "region")
    assert region.loading is False
    assert region.options[0].value == "ap-southeast-1"


def test_public_s3_bucket_fails_baseline_check():
    output = evaluate(
        {
            "resource_type": "s3_bucket",
            "check_level": "baseline",
            "region": "ap-southeast-1",
            "bucket_name": "reports",
            "public_access": True,
            "encryption": "sse-s3",
        },
        {},
        {"aws_regions": ["ap-southeast-1"]},
    )

    assert "Public S3 access" in field_by_id(output, "public_access").errors[0]
    assert output.can_submit is False


def test_security_group_rejects_world_open_ssh():
    output = evaluate(
        {
            "resource_type": "security_group",
            "check_level": "baseline",
            "region": "ap-southeast-1",
            "port": 22,
            "cidr": "0.0.0.0/0",
        },
        {},
        {"aws_regions": ["ap-southeast-1"]},
    )

    assert "SSH cannot be open" in field_by_id(output, "cidr").errors[0]
    assert output.can_submit is False


def test_security_group_validates_port_limits():
    output = evaluate(
        {
            "resource_type": "security_group",
            "check_level": "baseline",
            "region": "ap-southeast-1",
            "port": 70000,
            "cidr": "10.0.0.0/24",
        },
        {},
        {"aws_regions": ["ap-southeast-1"]},
    )

    assert "between 1 and 65535" in field_by_id(output, "port").errors[0]
    assert output.can_submit is False


def test_security_group_validates_cidr_format():
    output = evaluate(
        {
            "resource_type": "security_group",
            "check_level": "baseline",
            "region": "ap-southeast-1",
            "port": 443,
            "cidr": "not-a-cidr",
        },
        {},
        {"aws_regions": ["ap-southeast-1"]},
    )

    assert "CIDR must be a valid" in field_by_id(output, "cidr").errors[0]
    assert output.can_submit is False


def test_security_group_rejects_public_database_ports():
    output = evaluate(
        {
            "resource_type": "security_group",
            "check_level": "baseline",
            "region": "ap-southeast-1",
            "port": 5432,
            "cidr": "0.0.0.0/0",
        },
        {},
        {"aws_regions": ["ap-southeast-1"]},
    )

    assert "PostgreSQL cannot be open" in field_by_id(output, "cidr").errors[0]
    assert output.can_submit is False


def test_s3_validates_bucket_name_and_encryption():
    output = evaluate(
        {
            "resource_type": "s3_bucket",
            "check_level": "baseline",
            "region": "ap-southeast-1",
            "bucket_name": "Bad_Bucket",
            "public_access": False,
            "encryption": "none",
        },
        {},
        {"aws_regions": ["ap-southeast-1"]},
    )

    assert "Bucket name must" in field_by_id(output, "bucket_name").errors[0]
    assert "default encryption" in field_by_id(output, "encryption").errors[0]
    assert output.can_submit is False


def test_iam_role_validates_role_name():
    output = evaluate(
        {
            "resource_type": "iam_role",
            "check_level": "baseline",
            "role_name": "role with spaces",
        },
        {},
        {},
    )

    assert "Role name must" in field_by_id(output, "role_name").errors[0]
    assert output.can_submit is False


def test_hidden_fields_are_stripped_from_submit_payload():
    state = {
        "resource_type": "iam_role",
        "check_level": "baseline",
        "role_name": "readonly",
        "bucket_name": "hidden-bucket",
    }
    output = evaluate(state, {}, {})

    assert strip_hidden_fields(output.fields, state) == {
        "resource_type": "iam_role",
        "check_level": "baseline",
        "role_name": "readonly",
        "admin_policy": False,
    }


def test_async_request_resolver_returns_result_by_request_id():
    result = resolve_async_request(
        AsyncRequest(id="aws_regions", type="aws_regions_lookup")
    )

    assert result.id == "aws_regions"
    assert "ap-southeast-1" in result.result
