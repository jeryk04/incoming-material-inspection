import os
import sys
import tempfile
import unittest

import fitz
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from main import build_material_info
from report_generator import (
    _build_combined_properties_table,
    _clean_mechanical_label,
    _format_mechanical_value,
    create_inspection_pdf,
)


def _base_data(certificate):
    return {
        "material_info": {
            "supplier": "Supplier",
            "item_number": "ITEM-1",
            "part_number": "ITEM-1",
            "po_number": "123",
            "heat_number": "H1",
        },
        "certificate": certificate,
        "validation": {},
    }


def _table_text(material_info):
    flowables = _build_combined_properties_table(material_info, pd.DataFrame())
    text = []
    for flowable in flowables:
        for row in getattr(flowable, "_cellvalues", []):
            for cell in row:
                if hasattr(cell, "getPlainText"):
                    text.append(cell.getPlainText())
                elif isinstance(cell, list):
                    text.extend(
                        item.getPlainText()
                        for item in cell
                        if hasattr(item, "getPlainText")
                    )
                else:
                    text.append(str(cell))
    return "\n".join(text)


class CertificateMaterialPropertiesTests(unittest.TestCase):
    def test_all_mechanical_values_are_visible(self):
        info = build_material_info(_base_data({
            "yield_strength": "55000 PSI",
            "tensile_strength": "65000 PSI",
            "elongation": "17%",
            "hardness": "94 HRB",
            "mechanical_specified": {
                "yield_strength": "55000 Min",
                "tensile_strength": "65000 Min",
                "elongation": "10 Min",
                "hardness": "75 Min",
            },
        }))

        text = _table_text(info)

        self.assertIn("Yield", text)
        self.assertIn("Tensile", text)
        self.assertIn("Elongation", text)
        self.assertIn("Hardness", text)

    def test_missing_mechanical_values_are_omitted(self):
        info = build_material_info(_base_data({
            "yield_strength": "522",
            "tensile_strength": "572",
            "elongation": "",
            "hardness": "",
            "mechanical_specified": {
                "yield_strength": "490 Min",
                "tensile_strength": "550 Min",
                "elongation": "25 Min",
                "hardness": "75 Min",
            },
        }))

        text = _table_text(info)

        self.assertIn("Yield", text)
        self.assertIn("Tensile", text)
        self.assertNotIn("Elongation", text)
        self.assertNotIn("Hardness", text)

    def test_dynamic_mechanical_certificate_columns_are_visible(self):
        info = build_material_info(_base_data({
            "mechanical_properties": [
                {
                    "property": "Yield 0.2",
                    "observed": "287",
                    "unit": "N/mm2",
                },
                {
                    "property": "Yield 1.0",
                    "observed": "N/A",
                    "unit": "N/mm2",
                },
                {
                    "property": "Tensile",
                    "observed": "586",
                    "unit": "N/mm2",
                },
                {
                    "property": "Hardness",
                    "observed": "79",
                    "unit": "HRB",
                },
                {
                    "property": "Elongation",
                    "observed": "54.00",
                    "unit": "%",
                },
                {
                    "property": "Reduction",
                    "observed": "N/A",
                    "unit": "%",
                },
                {
                    "property": "Eddy Current Test",
                    "observed": "OK",
                },
            ],
        }))

        text = _table_text(info)

        self.assertIn("Yield 0.2", text)
        self.assertIn("Yield 1.0", text)
        self.assertIn("Tensile", text)
        self.assertIn("Hardness", text)
        self.assertIn("Elongation", text)
        self.assertIn("Reduction", text)
        self.assertIn("287", text)
        self.assertIn("N/A", text)
        self.assertNotIn("Eddy Current", text)

    def test_mechanical_display_removes_duplicate_units_and_formats_numbers(self):
        self.assertEqual(_clean_mechanical_label("Yield Strength (PSI)"), "Yield Strength")
        self.assertEqual(_clean_mechanical_label("Hardness (HRB) Min"), "Hardness")
        self.assertEqual(_format_mechanical_value("55000 PSI Min"), "55,000 Min")
        self.assertEqual(_format_mechanical_value("65000"), "65,000")
        self.assertEqual(_format_mechanical_value("93.0 - 94.0 HRB"), "93.0 - 94.0")

        info = build_material_info(_base_data({
            "mechanical_properties": [
                {
                    "property": "Yield Strength (PSI)",
                    "specified": "55000 PSI Min",
                    "observed": "55000",
                    "unit": "PSI",
                },
                {
                    "property": "Hardness (HRB) Min",
                    "specified": "75 HRB Min",
                    "observed": "93.0 - 94.0 HRB",
                    "unit": "HRB",
                },
            ],
        }))

        text = _table_text(info)

        self.assertIn("Yield Strength", text)
        self.assertIn("Hardness", text)
        self.assertIn("55,000", text)
        self.assertIn("93.0 - 94.0", text)
        self.assertNotIn("Yield Strength (PSI) (PSI)", text)
        self.assertNotIn("Hardness (HRB) Min", text)

    def test_absent_mechanical_tokens_are_omitted(self):
        info = build_material_info(_base_data({
            "yield_strength": "N.A",
            "tensile_strength": "Not Tested",
            "elongation": "N.S",
            "hardness": "94 HRB",
        }))

        text = _table_text(info)

        self.assertNotIn("Yield", text)
        self.assertNotIn("Tensile", text)
        self.assertNotIn("Elongation", text)
        self.assertIn("Hardness", text)

    def test_chemical_keys_are_canonicalized(self):
        info = build_material_info(_base_data({
            "chemical_composition": {
                "carbon": "0.20",
                "MANGANESE": "0.50",
                "si": "N.S",
            },
            "chemical_specified": {
                "Carbon": "0.25 Max",
                "mn": "1.20 Max",
            },
        }))

        text = _table_text(info)

        self.assertIn("C", text)
        self.assertIn("Mn", text)
        self.assertIn("0.20", text)
        self.assertIn("0.50", text)
        self.assertNotIn("Si", text)

    def test_nominal_dimension_without_explicit_cert_spec_is_omitted(self):
        info = build_material_info(_base_data({
            "outside_diameter": "0.340 INCH OD",
            "dimensional_specified": {},
        }))

        text = _table_text(info)

        self.assertNotIn("DIMENSIONAL PROPERTIES", text)
        self.assertNotIn("OD", text)

    def test_combined_absent_dimension_tokens_are_omitted(self):
        info = build_material_info(_base_data({
            "outside_diameter": "N.S / N.A",
            "dimensional_specified": {
                "outside_diameter": "N.S / N.A",
            },
        }))

        text = _table_text(info)

        self.assertNotIn("DIMENSIONAL PROPERTIES", text)
        self.assertNotIn("OD", text)

    def test_explicit_dimension_is_visible(self):
        info = build_material_info(_base_data({
            "outside_diameter": "0.340 / 0.341",
            "dimensional_specified": {
                "outside_diameter": "+0.005 / -0.005",
            },
        }))

        text = _table_text(info)

        self.assertIn("DIMENSIONAL PROPERTIES", text)
        self.assertIn("OD", text)
        self.assertIn("0.340 / 0.341", text)

    def test_existing_sample_can_generate_pdf_without_ai(self):
        data = _base_data({
            "yield_strength": "55000 PSI",
            "tensile_strength": "65000 PSI",
            "chemical_composition": {"C": "0.1935", "Mn": "0.470"},
            "chemical_specified": {"C": "0.18 - 0.23", "Mn": "0.3 - 0.7"},
        })
        info = build_material_info(data)

        with tempfile.TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "report.pdf")
            create_inspection_pdf(
                output_path,
                info,
                pd.DataFrame(),
                pd.DataFrame(),
                "LOT ACCEPTED",
            )
            self.assertTrue(os.path.isfile(output_path))
            self.assertGreater(os.path.getsize(output_path), 0)
            with fitz.open(output_path) as doc:
                text = "\n".join(page.get_text() for page in doc)
            self.assertIn("generated by AI", text)
            self.assertIn("supplier material test certificate", text)


if __name__ == "__main__":
    unittest.main()
