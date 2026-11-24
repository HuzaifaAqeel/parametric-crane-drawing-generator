"""Crane model: validation, derived values and SVG drawing.

Single-girder, top-running EOT overhead crane. All metric.
Pure logic only, no web code, so it can be unit tested on its own.

Formula sources are documented in README.md. Values that are
engineering estimates are labelled ESTIMATE wherever they are shown.
"""

import html
import math

DUTY_CLASSES = ("A3", "A4", "A5")
DEPTH_FACTORS = {"A3": 20, "A4": 18, "A5": 16}

E_PA = 200e9          # Young's modulus for steel, Pa
STEEL_DENSITY = 7850  # kg/m3
G = 9.81              # m/s2


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_inputs(data):
    """Validate a raw inputs dict. Returns (cleaned_inputs, errors).

    cleaned_inputs is None when there are errors. Never trusts the client.
    """
    errors = {}
    if not isinstance(data, dict):
        return None, {"body": "Request body must be a JSON object."}

    cleaned = {}

    # name: required string, 3-80 chars
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors["name"] = "Name is required."
    elif len(name.strip()) < 3:
        errors["name"] = "Name must be at least 3 characters."
    elif len(name.strip()) > 80:
        errors["name"] = "Name must be at most 80 characters."
    else:
        cleaned["name"] = name.strip()

    def number_field(field, low, high, required=True, default=None):
        value = data.get(field)
        if value is None:
            if required:
                errors[field] = "%s is required." % field
            elif default is not None:
                cleaned[field] = default
            return None
        if not _is_number(value):
            errors[field] = "%s must be a number." % field
            return None
        if isinstance(value, float) and not math.isfinite(value):
            errors[field] = "%s must be a finite number." % field
            return None
        if value < low or value > high:
            errors[field] = "%s must be between %s and %s." % (field, low, high)
            return None
        cleaned[field] = float(value)
        return float(value)

    span = number_field("span_m", 5, 30)
    number_field("capacity_t", 1, 20)
    number_field("lift_height_m", 3, 18)

    # trolley_position_m: optional, defaults to span/2, must sit 1.0 m
    # inside each end of the span.
    trolley = data.get("trolley_position_m")
    if trolley is None:
        if span is not None:
            cleaned["trolley_position_m"] = round(span / 2, 3)
    else:
        if not _is_number(trolley):
            errors["trolley_position_m"] = "trolley_position_m must be a number."
        elif isinstance(trolley, float) and not math.isfinite(trolley):
            errors["trolley_position_m"] = "trolley_position_m must be a finite number."
        elif span is not None and (trolley < 1.0 or trolley > span - 1.0):
            errors["trolley_position_m"] = (
                "trolley_position_m must be between 1.0 and %.3f for this span."
                % (span - 1.0)
            )
        elif span is None:
            errors["trolley_position_m"] = (
                "trolley_position_m cannot be checked without a valid span_m."
            )
        else:
            cleaned["trolley_position_m"] = float(trolley)

    # duty_class: enum, default A4
    duty = data.get("duty_class")
    if duty is None:
        cleaned["duty_class"] = "A4"
    elif duty not in DUTY_CLASSES:
        errors["duty_class"] = "duty_class must be one of A3, A4, A5."
    else:
        cleaned["duty_class"] = duty

    # notes: optional string, max 500 chars
    notes = data.get("notes")
    if notes is None:
        cleaned["notes"] = ""
    elif not isinstance(notes, str):
        errors["notes"] = "notes must be a string."
    elif len(notes) > 500:
        errors["notes"] = "notes must be at most 500 characters."
    else:
        cleaned["notes"] = notes

    if errors:
        return None, errors
    return cleaned, {}


def derive(inputs):
    """Compute derived values from validated inputs. Returns a dict."""
    span = inputs["span_m"]
    capacity = inputs["capacity_t"]
    lift = inputs["lift_height_m"]
    duty = inputs["duty_class"]

    depth_factor = DEPTH_FACTORS[duty]
    girder_depth = min(max(span / depth_factor, 0.40), 1.90)
    girder_width = girder_depth * 0.55
    plate_t_mm = 10 if capacity <= 5 else 12 if capacity <= 10 else 16
    t = plate_t_mm / 1000.0

    headroom = 0.85 + 0.04 * capacity          # ESTIMATE
    hook_block_h = 0.50 + 0.025 * capacity     # ESTIMATE
    end_carriage_h = 0.45                      # ESTIMATE
    girder_bottom = lift + headroom
    rail_top = girder_bottom - end_carriage_h
    trolley_h = 0.35 + 0.02 * capacity         # ESTIMATE
    overall_height = girder_bottom + girder_depth + trolley_h
    overhang = 0.60                            # ESTIMATE, each side
    overall_width = span + 2 * overhang
    end_carriage_len = min(max(1.8 + 0.04 * span, 2.0), 3.2)
    trolley_w = 0.80 + 0.03 * capacity         # ESTIMATE
    trolley_travel = span - 1.80               # ESTIMATE
    approach = 0.90                            # ESTIMATE

    # Box-section second moment of area, standard beam theory.
    outer_b, outer_d = girder_width, girder_depth
    inner_b, inner_d = outer_b - 2 * t, outer_d - 2 * t
    inertia = (outer_b * outer_d ** 3 - inner_b * inner_d ** 3) / 12.0
    load_n = capacity * 1000 * G
    deflection_live_mm = load_n * span ** 3 / (48 * E_PA * inertia) * 1000
    deflection_limit_mm = span * 1000 / 750.0
    deflection_ok = deflection_live_mm <= deflection_limit_mm

    # Mass estimates (ESTIMATE).
    area = 2 * (girder_width * t) + 2 * (girder_depth * t)
    girder_mass = area * span * STEEL_DENSITY
    end_carriage_mass_each = 220 + 8 * span
    trolley_mass = 350 + 55 * capacity
    total_mass = girder_mass + 2 * end_carriage_mass_each + trolley_mass

    max_wheel_load_kn = ((total_mass + capacity * 1000) * G / 4 * 1.15) / 1000

    def r3(value):
        return round(float(value), 3)

    return {
        "depth_factor": depth_factor,
        "girder_depth_m": r3(girder_depth),
        "girder_width_m": r3(girder_width),
        "plate_t_mm": plate_t_mm,
        "headroom_m": r3(headroom),
        "hook_block_h_m": r3(hook_block_h),
        "end_carriage_h_m": r3(end_carriage_h),
        "girder_bottom_m": r3(girder_bottom),
        "rail_top_m": r3(rail_top),
        "trolley_h_m": r3(trolley_h),
        "overall_height_m": r3(overall_height),
        "overhang_m": r3(overhang),
        "overall_width_m": r3(overall_width),
        "end_carriage_len_m": r3(end_carriage_len),
        "trolley_w_m": r3(trolley_w),
        "trolley_travel_m": r3(trolley_travel),
        "approach_m": r3(approach),
        "moment_of_inertia_m4": round(inertia, 8),
        "deflection_live_mm": round(deflection_live_mm, 2),
        "deflection_limit_mm": round(deflection_limit_mm, 2),
        "deflection_ok": bool(deflection_ok),
        "girder_mass_kg": round(girder_mass),
        "end_carriage_mass_each_kg": round(end_carriage_mass_each),
        "trolley_hoist_mass_kg": round(trolley_mass),
        "total_mass_kg": round(total_mass),
        "max_wheel_load_kn": round(max_wheel_load_kn, 1),
    }


# ---------------------------------------------------------------- SVG drawing

def _fmt(value):
    return "%.2f" % value


def build_svg(inputs, derived):
    """Build one dimensioned SVG (viewBox 0 0 1100 1250) with three panels."""
    span = inputs["span_m"]
    capacity = inputs["capacity_t"]
    lift = inputs["lift_height_m"]
    trolley = inputs["trolley_position_m"]
    name = html.escape(inputs["name"])

    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 1250" '
        'width="1100" height="1250" font-family="Arial, Helvetica, sans-serif">'
    )
    parts.append(
        '<defs>'
        '<marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="4" '
        'orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#1f4e79"/></marker>'
        '<marker id="arr-r" markerWidth="8" markerHeight="8" refX="1" refY="4" '
        'orient="auto"><path d="M8,0 L0,4 L8,8 z" fill="#1f4e79"/></marker>'
        '</defs>'
    )
    parts.append('<rect x="0" y="0" width="1100" height="1250" fill="#ffffff"/>')
    parts.append(
        '<text x="550" y="34" text-anchor="middle" font-size="20" '
        'font-weight="bold" fill="#1f4e79">%s</text>' % name
    )
    parts.append(
        '<text x="550" y="56" text-anchor="middle" font-size="12" fill="#555555">'
        'Single-girder top-running EOT crane  |  SWL %s t  |  Duty %s  |  '
        'All dimensions in metres unless noted</text>'
        % (_fmt(capacity), html.escape(inputs["duty_class"]))
    )

    parts.append(_front_panel(inputs, derived))
    parts.append(_side_panel(inputs, derived))
    parts.append(_plan_panel(inputs, derived))

    parts.append(
        '<text x="550" y="1238" text-anchor="middle" font-size="11" fill="#777777">'
        'Drawing generated from inputs. Values marked estimate are rules of '
        'thumb, not for manufacture.</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _dim_h(out, x1, x2, y, label, ext1=None, ext2=None):
    """Horizontal dimension line with arrowheads and a label above it."""
    if ext1 is not None:
        out.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#9bb3c8" '
            'stroke-width="1"/>' % (x1, ext1, x1, y)
        )
    if ext2 is not None:
        out.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#9bb3c8" '
            'stroke-width="1"/>' % (x2, ext2, x2, y)
        )
    out.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#1f4e79" '
        'stroke-width="1.2" marker-start="url(#arr-r)" '
        'marker-end="url(#arr)"/>' % (x1, y, x2, y)
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="12" '
        'fill="#1f4e79">%s</text>' % ((x1 + x2) / 2, y - 5, html.escape(label))
    )


def _dim_v(out, y1, y2, x, label, ext1=None, ext2=None):
    """Vertical dimension line with arrowheads and a rotated label."""
    if ext1 is not None:
        out.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#9bb3c8" '
            'stroke-width="1"/>' % (ext1, y1, x, y1)
        )
    if ext2 is not None:
        out.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#9bb3c8" '
            'stroke-width="1"/>' % (ext2, y2, x, y2)
        )
    out.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#1f4e79" '
        'stroke-width="1.2" marker-start="url(#arr-r)" '
        'marker-end="url(#arr)"/>' % (x, y1, x, y2)
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="12" '
        'fill="#1f4e79" transform="rotate(-90 %.1f %.1f)">%s</text>'
        % (x - 6, (y1 + y2) / 2, x - 6, (y1 + y2) / 2, html.escape(label))
    )


def _panel_title(out, x, y, text):
    out.append(
        '<text x="%.1f" y="%.1f" font-size="14" font-weight="bold" '
        'fill="#1f4e79">%s</text>' % (x, y, text)
    )


def _front_panel(inputs, d):
    span = inputs["span_m"]
    lift = inputs["lift_height_m"]
    trolley = inputs["trolley_position_m"]
    out = []
    # Panel box: x 40..1060, y 70..500. Title at y 88.
    _panel_title(out, 40, 88, "A) FRONT ELEVATION")
    ox, floor_y = 130.0, 420.0
    avail_w, avail_h = 820.0, 290.0
    scale = min(
        avail_w / (d["overall_width_m"] + 1.0),
        avail_h / (d["overall_height_m"] + 1.0),
    )

    def X(m):
        return ox + (m + d["overhang_m"]) * scale

    def Y(m):
        return floor_y - m * scale

    rail_top = d["rail_top_m"]
    girder_bottom = d["girder_bottom_m"]
    girder_top = girder_bottom + d["girder_depth_m"]
    trolley_top = girder_top + d["trolley_h_m"]
    hook_bottom = lift
    hook_top = lift + d["hook_block_h_m"]

    # Floor line
    out.append(
        '<line x1="40" y1="%.1f" x2="1060" y2="%.1f" stroke="#333333" '
        'stroke-width="2"/>' % (floor_y, floor_y)
    )
    out.append(
        '<text x="46" y="%.1f" font-size="11" fill="#555555">FLOOR</text>'
        % (floor_y + 16)
    )
    # Runway rails (small blocks at the span ends)
    for cx in (0.0, span):
        out.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#8a9ba8" '
            'stroke="#1f4e79" stroke-width="1"/>'
            % (X(cx) - 0.075 * scale, Y(rail_top), 0.15 * scale, 0.12 * scale)
        )
    out.append(
        '<text x="%.1f" y="%.1f" font-size="11" fill="#555555">RUNWAY RAIL</text>'
        % (X(0) - 4, Y(rail_top) + 16)
    )
    # End carriages (blocks under the girder ends)
    for cx in (0.0, span):
        out.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#c9d6e2" '
            'stroke="#1f4e79" stroke-width="1.2"/>'
            % (
                X(cx) - 0.25 * scale,
                Y(girder_bottom),
                0.50 * scale,
                d["end_carriage_h_m"] * scale,
            )
        )
    # Girder
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#dce8f2" '
        'stroke="#1f4e79" stroke-width="1.5"/>'
        % (X(0), Y(girder_top), span * scale, d["girder_depth_m"] * scale)
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="12" '
        'fill="#1f4e79">GIRDER</text>'
        % (X(span * 0.25), Y(girder_bottom) + d["girder_depth_m"] * scale / 2 + 4)
    )
    # Trolley on top of the girder
    tw = d["trolley_w_m"]
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#9bb3c8" '
        'stroke="#1f4e79" stroke-width="1.2"/>'
        % (
            X(trolley) - tw / 2 * scale,
            Y(trolley_top),
            tw * scale,
            d["trolley_h_m"] * scale,
        )
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="11" '
        'fill="#1f4e79">TROLLEY</text>'
        % (X(trolley), Y(trolley_top) - 5)
    )
    # Hoist rope from trolley down to the hook block
    out.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#1f4e79" '
        'stroke-width="1.5"/>' % (X(trolley), Y(girder_top), X(trolley), Y(hook_top))
    )
    # Hook block and hook
    hb_w = 0.45
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#c9d6e2" '
        'stroke="#1f4e79" stroke-width="1.2"/>'
        % (
            X(trolley) - hb_w / 2 * scale,
            Y(hook_top),
            hb_w * scale,
            d["hook_block_h_m"] * scale,
        )
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="end" font-size="11" '
        'fill="#1f4e79">HOOK BLOCK</text>'
        % (X(trolley) - hb_w / 2 * scale - 8, Y(hook_top) + d["hook_block_h_m"] * scale / 2 + 4)
    )
    out.append(
        '<path d="M %.1f %.1f q 0 14 -9 14 q -9 0 -9 -9" fill="none" '
        'stroke="#1f4e79" stroke-width="2"/>'
        % (X(trolley), Y(hook_bottom))
    )
    out.append(
        '<text x="%.1f" y="%.1f" font-size="11" fill="#555555">HOOK</text>'
        % (X(trolley) + 12, Y(hook_bottom) + 16)
    )

    # Dimensions
    _dim_h(
        out, X(0), X(span), floor_y + 34,
        "SPAN %s m" % _fmt(span), ext1=Y(rail_top), ext2=Y(rail_top),
    )
    _dim_h(
        out, X(-d["overhang_m"]), X(span + d["overhang_m"]), floor_y + 58,
        "OVERALL WIDTH %s m" % _fmt(d["overall_width_m"]),
        ext1=Y(girder_bottom), ext2=Y(girder_bottom),
    )
    _dim_v(
        out, Y(d["overall_height_m"]), floor_y, 72,
        "OVERALL HEIGHT %s m" % _fmt(d["overall_height_m"]),
        ext1=X(span + d["overhang_m"]), ext2=X(span + d["overhang_m"]),
    )
    hook_x = X(trolley) + 0.55 * scale
    _dim_v(
        out, Y(hook_bottom), floor_y, hook_x,
        "LIFT HEIGHT %s m" % _fmt(lift),
        ext1=X(trolley) + 0.25 * scale, ext2=X(trolley) + 0.25 * scale,
    )
    gd_x = X(span) + 0.45 * scale
    _dim_v(
        out, Y(girder_top), Y(girder_bottom), gd_x,
        "GIRDER DEPTH %s m" % _fmt(d["girder_depth_m"]),
        ext1=X(span), ext2=X(span),
    )
    return "".join(out)


def _side_panel(inputs, d):
    out = []
    _panel_title(out, 40, 545, "B) SIDE ELEVATION")
    ox, floor_y = 200.0, 800.0
    avail_w, avail_h = 420.0, 220.0
    scale = min(
        avail_w / (d["end_carriage_len_m"] + 1.0),
        avail_h / (d["overall_height_m"] + 1.0),
    )

    def X(m):
        return ox + m * scale

    def Y(m):
        return floor_y - m * scale

    rail_top = d["rail_top_m"]
    girder_bottom = d["girder_bottom_m"]
    girder_top = girder_bottom + d["girder_depth_m"]
    trolley_top = girder_top + d["trolley_h_m"]

    out.append(
        '<line x1="40" y1="%.1f" x2="1060" y2="%.1f" stroke="#333333" '
        'stroke-width="2"/>' % (floor_y, floor_y)
    )
    # End carriage (length along the runway)
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#c9d6e2" '
        'stroke="#1f4e79" stroke-width="1.2"/>'
        % (
            X(0),
            Y(girder_bottom),
            d["end_carriage_len_m"] * scale,
            d["end_carriage_h_m"] * scale,
        )
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="end" font-size="11" '
        'fill="#1f4e79">END CARRIAGE</text>'
        % (X(0) - 10, Y(girder_bottom) + d["end_carriage_h_m"] * scale / 2 + 4)
    )
    # Girder width (seen end-on)
    gw = d["girder_width_m"]
    gx = X(d["end_carriage_len_m"] / 2) - gw / 2 * scale
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#dce8f2" '
        'stroke="#1f4e79" stroke-width="1.5"/>'
        % (gx, Y(girder_top), gw * scale, d["girder_depth_m"] * scale)
    )
    out.append(
        '<text x="%.1f" y="%.1f" font-size="11" '
        'fill="#1f4e79">GIRDER WIDTH %s m</text>'
        % (gx + gw * scale + 8, Y(girder_top) + d["girder_depth_m"] * scale / 2 + 4, _fmt(gw))
    )
    # Trolley width (seen end-on)
    tw = d["trolley_w_m"]
    tx = X(d["end_carriage_len_m"] / 2) - tw / 2 * scale
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#9bb3c8" '
        'stroke="#1f4e79" stroke-width="1.2"/>'
        % (tx, Y(trolley_top), tw * scale, d["trolley_h_m"] * scale)
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="11" '
        'fill="#1f4e79">TROLLEY WIDTH %s m</text>'
        % (X(d["end_carriage_len_m"] / 2), Y(trolley_top) - 6, _fmt(tw))
    )
    # Dimensions
    _dim_h(
        out, X(0), X(d["end_carriage_len_m"]), floor_y + 30,
        "END CARRIAGE LENGTH %s m" % _fmt(d["end_carriage_len_m"]),
        ext1=Y(rail_top), ext2=Y(rail_top),
    )
    _dim_v(
        out, Y(d["overall_height_m"]), floor_y,
        X(d["end_carriage_len_m"]) + 170,
        "OVERALL HEIGHT %s m" % _fmt(d["overall_height_m"]),
        ext1=X(d["end_carriage_len_m"]), ext2=X(d["end_carriage_len_m"]),
    )
    return "".join(out)


def _plan_panel(inputs, d):
    span = inputs["span_m"]
    trolley = inputs["trolley_position_m"]
    out = []
    _panel_title(out, 40, 880, "C) PLAN (TOP VIEW)")
    ox, oy = 200.0, 930.0
    avail_w, avail_h = 700.0, 200.0
    scale = min(
        avail_w / (span + 1.0), avail_h / (d["end_carriage_len_m"] + 1.0)
    )
    w = span * scale
    h = d["end_carriage_len_m"] * scale

    # Outline: span x end-carriage length
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#f2f6fa" '
        'stroke="#1f4e79" stroke-width="1.5"/>' % (ox, oy, w, h)
    )
    # Girder centreline, dashed
    out.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#1f4e79" '
        'stroke-width="1" stroke-dasharray="8,5"/>'
        % (ox, oy + h / 2, ox + w, oy + h / 2)
    )
    out.append(
        '<text x="%.1f" y="%.1f" font-size="11" fill="#555555">'
        'GIRDER CENTRELINE</text>' % (ox + 20, oy + h / 2 - 8)
    )
    # Girder edges (dashed, girder width across the carriage length)
    gw_px = d["girder_width_m"] * scale
    for dy in (h / 2 - gw_px / 2, h / 2 + gw_px / 2):
        out.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#9bb3c8" '
            'stroke-width="1" stroke-dasharray="4,4"/>'
            % (ox, oy + dy, ox + w, oy + dy)
        )
    # Trolley square at trolley_position
    tw_px = d["trolley_w_m"] * scale
    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#9bb3c8" '
        'stroke="#1f4e79" stroke-width="1.2"/>'
        % (ox + trolley * scale - tw_px / 2, oy + h / 2 - tw_px / 2, tw_px, tw_px)
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="11" '
        'fill="#1f4e79">TROLLEY</text>'
        % (ox + trolley * scale, oy + h / 2 - tw_px / 2 - 6)
    )
    # Runway rails at each end (short vertical ticks)
    for cx in (ox, ox + w):
        out.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#8a9ba8" '
            'stroke-width="4"/>' % (cx, oy - 12, cx, oy + h + 12)
        )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="end" font-size="11" fill="#555555">RUNWAY RAIL</text>'
        % (ox - 10, oy + h / 2 + 4)
    )
    # Dimensions
    _dim_h(
        out, ox, ox + w, oy + h + 34,
        "SPAN %s m" % _fmt(span), ext1=oy, ext2=oy,
    )
    _dim_v(
        out, oy, oy + h, ox + w + 60,
        "END CARRIAGE LENGTH %s m" % _fmt(d["end_carriage_len_m"]),
        ext1=ox, ext2=ox,
    )
    return "".join(out)
