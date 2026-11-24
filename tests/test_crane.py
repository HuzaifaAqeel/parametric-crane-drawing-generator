"""Unit tests for crane.py: validation, derivation and SVG output."""

import math
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crane import build_svg, derive, validate_inputs


def base_inputs(**overrides):
    inputs = {
        "name": "Workshop Crane 5t",
        "span_m": 20,
        "capacity_t": 5,
        "lift_height_m": 6,
        "trolley_position_m": 10,
        "duty_class": "A4",
        "notes": "",
    }
    inputs.update(overrides)
    return inputs


class TestValidation(unittest.TestCase):
    def test_valid_inputs_pass(self):
        cleaned, errors = validate_inputs(base_inputs())
        self.assertEqual(errors, {})
        self.assertEqual(cleaned["span_m"], 20.0)
        self.assertEqual(cleaned["duty_class"], "A4")

    def test_trolley_defaults_to_midspan(self):
        data = base_inputs()
        del data["trolley_position_m"]
        cleaned, errors = validate_inputs(data)
        self.assertEqual(errors, {})
        self.assertEqual(cleaned["trolley_position_m"], 10.0)

    def test_span_too_large_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(span_m=40))
        self.assertIsNone(cleaned)
        self.assertIn("span_m", errors)

    def test_capacity_zero_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(capacity_t=0))
        self.assertIsNone(cleaned)
        self.assertIn("capacity_t", errors)

    def test_trolley_outside_range_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(trolley_position_m=19.5))
        self.assertIsNone(cleaned)
        self.assertIn("trolley_position_m", errors)

    def test_bad_duty_class_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(duty_class="A9"))
        self.assertIsNone(cleaned)
        self.assertIn("duty_class", errors)

    def test_name_too_short_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(name="AB"))
        self.assertIsNone(cleaned)
        self.assertIn("name", errors)

    def test_non_finite_number_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(span_m=float("inf")))
        self.assertIsNone(cleaned)
        self.assertIn("span_m", errors)

    def test_notes_too_long_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(notes="x" * 501))
        self.assertIsNone(cleaned)
        self.assertIn("notes", errors)

    def test_wrong_type_rejected(self):
        cleaned, errors = validate_inputs(base_inputs(span_m="twenty"))
        self.assertIsNone(cleaned)
        self.assertIn("span_m", errors)


class TestDerivation(unittest.TestCase):
    def test_girder_depth_span_20_cap_5_a4(self):
        cleaned, _ = validate_inputs(base_inputs())
        d = derive(cleaned)
        self.assertAlmostEqual(d["girder_depth_m"], 20 / 18, places=3)
        self.assertAlmostEqual(d["girder_width_m"], (20 / 18) * 0.55, places=3)
        self.assertEqual(d["plate_t_mm"], 10)
        self.assertAlmostEqual(d["overall_width_m"], 21.20, places=3)
        self.assertAlmostEqual(d["girder_bottom_m"], 6 + 0.85 + 0.04 * 5, places=3)
        self.assertAlmostEqual(d["rail_top_m"], d["girder_bottom_m"] - 0.45, places=3)

    def test_deflection_positive_and_limit_correct(self):
        cleaned, _ = validate_inputs(base_inputs())
        d = derive(cleaned)
        self.assertGreater(d["deflection_live_mm"], 0)
        self.assertAlmostEqual(d["deflection_limit_mm"], 20000 / 750, places=2)
        # Independent recomputation of the beam formula
        b, depth = d["girder_width_m"], d["girder_depth_m"]
        t = d["plate_t_mm"] / 1000.0
        inertia = (b * depth ** 3 - (b - 2 * t) * (depth - 2 * t) ** 3) / 12.0
        expected = 5 * 1000 * 9.81 * 20 ** 3 / (48 * 200e9 * inertia) * 1000
        self.assertAlmostEqual(d["deflection_live_mm"], expected, places=1)

    def test_plate_thickness_steps(self):
        for capacity, expected_t in ((5, 10), (8, 12), (15, 16)):
            cleaned, _ = validate_inputs(base_inputs(capacity_t=capacity))
            self.assertEqual(derive(cleaned)["plate_t_mm"], expected_t)

    def test_duty_class_changes_depth(self):
        for duty, factor in (("A3", 20), ("A4", 18), ("A5", 16)):
            cleaned, _ = validate_inputs(base_inputs(duty_class=duty))
            d = derive(cleaned)
            self.assertAlmostEqual(d["girder_depth_m"], 20 / factor, places=3)

    def test_masses_and_wheel_load_positive(self):
        cleaned, _ = validate_inputs(base_inputs())
        d = derive(cleaned)
        self.assertGreater(d["total_mass_kg"], 0)
        self.assertGreater(d["max_wheel_load_kn"], 0)
        self.assertEqual(
            d["total_mass_kg"],
            d["girder_mass_kg"] + 2 * d["end_carriage_mass_each_kg"]
            + d["trolley_hoist_mass_kg"],
        )


class TestSvg(unittest.TestCase):
    def test_svg_contains_dimension_labels(self):
        cleaned, _ = validate_inputs(base_inputs())
        svg = build_svg(cleaned, derive(cleaned))
        self.assertIn("SPAN 20.00 m", svg)
        self.assertIn("LIFT HEIGHT", svg)
        self.assertIn("OVERALL HEIGHT", svg)
        self.assertIn("GIRDER DEPTH", svg)
        self.assertIn("END CARRIAGE LENGTH", svg)

    def test_svg_parses_as_xml(self):
        cleaned, _ = validate_inputs(base_inputs())
        svg = build_svg(cleaned, derive(cleaned))
        root = ET.fromstring(svg)
        self.assertEqual(root.tag.split("}")[-1], "svg")
        self.assertEqual(root.get("viewBox"), "0 0 1100 1250")

    def test_svg_escapes_user_text(self):
        cleaned, _ = validate_inputs(base_inputs(name="Test <b>& Crane"))
        svg = build_svg(cleaned, derive(cleaned))
        self.assertNotIn("<b>& Crane", svg)
        self.assertIn("Test &lt;b&gt;&amp; Crane", svg)


if __name__ == "__main__":
    unittest.main()
