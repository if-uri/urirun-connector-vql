# Author: Tom Sapletta · Part of the ifURI solution.
from __future__ import annotations

import json

from urirun_connector_vql import (
    CONNECTOR_ID,
    image_analyze,
    image_regions,
    urirun_bindings,
)

ROUTES = {
    "vql://host/image/query/analyze",
    "vql://host/image/query/regions",
    "vql://host/image/query/diagnose",
}


def test_connector_id():
    assert CONNECTOR_ID == "vql"


def test_bindings_serializable_and_complete():
    b = urirun_bindings()["bindings"]
    assert set(b) == ROUTES
    json.dumps(urirun_bindings())  # no live-ref leaks
    assert b["vql://host/image/query/analyze"]["adapter"] == "local-function"


def test_lazy_import_no_vql_at_module_top():
    import importlib
    import sys

    for m in [m for m in list(sys.modules) if m == "vql" or m.startswith("vql.")]:
        del sys.modules[m]
    importlib.reload(importlib.import_module("urirun_connector_vql.core"))
    assert "vql" not in sys.modules, "connector import pulled vql eagerly"


def test_analyze_requires_image():
    assert image_analyze(image="")["ok"] is False


def test_regions_requires_image():
    assert image_regions(image="")["ok"] is False


def test_missing_image_returns_envelope():
    r = image_analyze(image="/nonexistent/frame.png")
    assert r["ok"] is False and "error" in r  # never raises
