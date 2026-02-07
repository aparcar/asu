#!/usr/bin/env python3
"""Validate YAML config files against their JSON schemas."""

import json
import sys

import jsonschema
import yaml

CHECKS = [
    ("asu.yaml", "asu_schema.json"),
]

errors = 0
for yaml_file, schema_file in CHECKS:
    with open(schema_file) as f:
        schema = json.load(f)
    with open(yaml_file) as f:
        data = yaml.safe_load(f)
    try:
        jsonschema.validate(data, schema)
        print(f"{yaml_file}: OK")
    except jsonschema.ValidationError as e:
        print(f"{yaml_file}: FAILED - {e.message}")
        errors += 1

sys.exit(1 if errors else 0)
