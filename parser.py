import yaml
import re
from typing import Any

def _to_snake_case(name: str) -> str:
    """Convert a string to snake_case."""
    name = re.sub(r"[/{}\-]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    # Convert camelCase to snake_case
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return name.lower()

def _build_input_schema(parameters: list, request_body: dict | None) -> dict:
    """Build a JSON Schema from parameters and requestBody."""
    properties = {}
    required = []

    for param in parameters:
        schema = param.get("schema", {"type": "string"})
        prop = {**schema, "description": param.get("description", f"{param['name']} ({param['in']} parameter)")}
        properties[param["name"]] = prop
        if param.get("required", False):
            required.append(param["name"])

    if request_body:
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        body_schema = json_content.get("schema", {"type": "object"})
        properties["body"] = {**body_schema, "description": request_body.get("description", "Request body")}
        if request_body.get("required", False):
            required.append("body")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }

def parse_openapi(file_path: str, base_url_override: str | None = None) -> dict:
    """Parse an OpenAPI YAML file and return structured operation data."""
    with open(file_path, "r") as f:
        spec = yaml.safe_load(f)

    # Extract base URL
    servers = spec.get("servers", [])
    base_url = base_url_override or (servers[0]["url"] if servers else "http://localhost")

    # Extract global auth schemes
    auth_schemes = spec.get("components", {}).get("securitySchemes", {})

    # Extract global security requirements
    global_security = spec.get("security", [])

    operations = []
    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        # Path-level parameters
        path_level_params = path_item.get("parameters", [])

        for method in ["get", "post", "put", "delete", "patch", "head", "options"]:
            operation = path_item.get(method)
            if not operation:
                continue

            operation_id = operation.get("operationId")
            if operation_id:
                tool_name = _to_snake_case(operation_id)
            else:
                tool_name = _to_snake_case(f"{method}_{path}")

            # Merge path-level and operation-level parameters
            op_params = operation.get("parameters", [])
            param_names = {p["name"] for p in op_params}
            merged_params = op_params + [p for p in path_level_params if p["name"] not in param_names]

            # Resolve $ref in parameters (basic inline resolution)
            resolved_params = []
            for param in merged_params:
                if "$ref" in param:
                    ref_path = param["$ref"].replace("#/', '').split("/")
                    resolved = spec
                    for key in ref_path:
                        resolved = resolved.get(key, {})
                    resolved_params.append(resolved)
                else:
                    resolved_params.append(param)

            request_body = operation.get("requestBody")
            security = operation.get("security", global_security)

            input_schema = _build_input_schema(resolved_params, request_body)

            description = operation.get("summary") or operation.get("description") or f"{method.upper()} {path}"

            operations.append({
                "tool_name": tool_name,
                "description": description,
                "method": method,
                "path": path,
                "parameters": resolved_params,
                "request_body": request_body,
                "security": security,
                "input_schema": input_schema,
            })

    return {
        "base_url": base_url.rstrip("/"),
        "auth_schemes": auth_schemes,
        "operations": operations,
    }