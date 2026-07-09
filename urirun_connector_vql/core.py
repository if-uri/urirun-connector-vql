# Author: Tom Sapletta · Part of the ifURI solution.
"""urirun-connector-vql — native URI surface over the VQL (Visual Query Language) package.

vql analyses a screenshot into a structured scene: regions/objects with geometry, dominant
colours, a window title, and a scene class. It is the *visual understanding* layer that works
on GNOME-Wayland where window enumeration is blocked (it reads a screenshot, not the window
manager). It shipped only a thin ``uri2vql`` CLI/string bridge; this is a served connector so a
urirun node / flow / readiness kernel can compose vql:// with capture (kvm) and decision
(urivision) in a resolve-first plane.

Built to the URI-native connector checklist (urirun/docs/URI_NATIVE_CONNECTOR_CHECKLIST.md):
lazy imports (vql only inside handlers), handlers never raise (urirun envelope), read-only
analysis in-process, heavy deps optional.
"""
from __future__ import annotations

from typing import Any

import urirun

from . import _urirun_compat

CONNECTOR_ID = "vql"
conn = _urirun_compat.connector(CONNECTOR_ID, scheme="vql")


def _ok(**kw: Any) -> dict[str, Any]:
    return urirun.ok(connector=CONNECTOR_ID, **kw)


def _fail(msg: str, action: str, **extra: Any) -> dict[str, Any]:
    return urirun.fail(msg, connector=CONNECTOR_ID, action=action, **extra)


def _program_objects(result: dict) -> list[dict]:
    """The VQL program's regions live in the written program FILE (not the inline scene
    summary). Load them: each is a geometric region — id, primitives (w/h), style.color,
    center_x/center_y — NO text label (VQL grounds by geometry/colour, not OCR text)."""
    import json
    import os

    prog = result.get("program")
    if isinstance(prog, dict):
        scene = prog.get("scene") or {}
    elif isinstance(prog, str) and os.path.isfile(prog):
        try:
            scene = (json.load(open(prog)).get("scene")) or {}
        except Exception:  # noqa: BLE001
            return []
    else:
        scene = result.get("scene") or {}
    objs: list[dict] = []
    for layer in scene.get("layers") or []:
        objs.extend(layer.get("objects") or [])
    return objs


def _int(v: Any) -> int | None:
    return int(round(float(v))) if v is not None else None


def _region_summary(o: dict) -> dict:
    """Compact, click-ready view of a VQL region: center point + geometry + colour. ``center``
    is rounded to INTEGER pixels so it drops straight into a kvm click (whose x/y are ints) —
    VQL keeps sub-pixel floats internally, but a click target must be a pixel."""
    prim = (o.get("primitives") or [{}])[0].get("params") or {}
    return {
        "id": o.get("id"),
        "center": [_int(o.get("center_x")), _int(o.get("center_y"))],
        "width": _int(prim.get("width")), "height": _int(prim.get("height")),
        "color": (o.get("style") or {}).get("color"),
        "area": float(prim.get("width") or 0) * float(prim.get("height") or 0),
    }


@conn.handler("image/query/analyze", isolated=False,
              meta={"label": "Analyze a screenshot into a structured VQL scene (regions + title)"})
def image_analyze(image: str = "", grid: int = 12, locale: str = "en") -> dict[str, Any]:
    """Screenshot → structured scene: object/region geometry, dominant colours, window title,
    scene class. Wayland-proof grounding (reads pixels, not the window manager). Returns the
    scene summary + object_count; the full program is written to ``out_program`` on the node."""
    if not image:
        return _fail("image path is required", "vql-analyze")
    try:
        from vql.adopt.window import analyze_screenshot
        r = analyze_screenshot(image, grid=int(grid), locale=locale, skip_if_unchanged=False)
    except FileNotFoundError as exc:
        return _fail(str(exc), "vql-analyze")
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc), "vql-analyze")
    if not r.get("ok"):
        return _fail(r.get("error") or "analysis failed", "vql-analyze",
                     **{k: r.get(k) for k in ("hint", "recommendation", "image_stats") if k in r})
    return _ok(action="vql-analyze", image=r.get("image"),
               scene=r.get("scene"), object_count=r.get("object_count"),
               window_title=r.get("window_title"), scene_class=r.get("scene_class"),
               dominant_colors=r.get("dominant_colors"), special_hits=r.get("special_hits"))


@conn.handler("image/query/regions", isolated=False,
              meta={"label": "Rank scene regions by colour/size — click-ready centers (Wayland grounding)"})
def image_regions(image: str = "", color: str = "", min_area: int = 0, top: int = 12,
                  locale: str = "en") -> dict[str, Any]:
    """Vision grounding WITHOUT a window list: analyse the screenshot and return regions as
    click-ready centers, optionally filtered by ``color`` (hex prefix, e.g. ``#fff``) and
    ``min_area``, largest first. VQL grounds by geometry/colour, not OCR text — for text use
    kvm host-OCR; for 'the big blue panel' / 'the toolbar row' use this. Returns [{id, center,
    width, height, color, area}] so a caller maps straight to a kvm click point."""
    if not image:
        return _fail("image path is required", "vql-regions")
    try:
        from vql.adopt.window import analyze_screenshot
        r = analyze_screenshot(image, locale=locale, skip_if_unchanged=False)
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc), "vql-regions")
    if not r.get("ok"):
        return _fail(r.get("error") or "analysis failed", "vql-regions")
    regions = [_region_summary(o) for o in _program_objects(r)]
    if color:
        cl = color.lower()
        regions = [x for x in regions if str(x.get("color", "")).lower().startswith(cl)]
    if min_area:
        regions = [x for x in regions if x["area"] >= float(min_area)]
    regions.sort(key=lambda x: -x["area"])
    return _ok(action="vql-regions", count=len(regions), regions=regions[:int(top)],
               window_title=r.get("window_title"))


@conn.handler("image/query/diagnose", isolated=False,
              meta={"label": "Diagnose screenshot capture (is the frame usable for analysis)"})
def image_diagnose(image: str = "") -> dict[str, Any]:
    """Honest top-line before analysis: is the frame non-blank/usable. On GNOME-Wayland a
    blocked capture is all-black; this catches it so a resolver doesn't analyse a dead frame."""
    if not image:
        return _fail("image path is required", "vql-diagnose")
    try:
        from vql.adopt.capture_image import image_stats
        stats = image_stats(image)
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc), "vql-diagnose")
    return _ok(action="vql-diagnose", image=image, usable=not stats.get("is_blank"), **stats)


def urirun_bindings() -> dict[str, Any]:
    """Serializable v2 bindings (entry point: urirun.bindings)."""
    return conn.bindings()

@conn.handler("vql://host/doctor/query/report", isolated=True, meta={"label": "Connector readiness report"})
def doctor() -> dict[str, Any]:
    """Return a safe, read-only connector readiness report for CI smoke tests."""
    return {
        "ok": True,
        "connector": CONNECTOR_ID,
        "version": _connector_version(),
        "status": "ready",
    }


def _connector_version() -> str:
    try:
        from importlib.metadata import version

        return version("urirun-connector-vql")
    except Exception:
        return "0.1.0"


def connector_manifest() -> dict[str, Any]:
    """Manifest prose + a GENERATED per-URI capability list (URI_COMMAND_STANDARD.md §6): each
    route's class/verb/summary/mutates/errors, so every URI is self-describing and cannot drift
    from the served routes."""
    m = _urirun_compat.load_manifest(__package__) or {}
    try:
        from urirun_connectors_toolkit.connector_sdk import manifest_routes
        m["routes"] = manifest_routes(urirun_bindings())
    except Exception:  # noqa: BLE001 - routes list is enrichment; never break the manifest
        pass
    return m


def main(argv: list[str] | None = None) -> int:
    return conn.cli(argv, manifest_prose=_urirun_compat.load_manifest(__package__))


if __name__ == "__main__":
    raise SystemExit(main())
