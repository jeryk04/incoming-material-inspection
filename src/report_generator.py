"""
Professional Incoming Inspection Report PDF generator.

The report is structured around the same quality-review concepts shown on
supplier material certificates: traceability, dimensional inspection,
chemical properties, mechanical properties, notes, and final disposition.
"""

import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_LOGO_PATH = os.path.join(_PROJECT_ROOT, "assets", "logo.png")

COMPANY_NAME    = "G & J Steel & Tubing, Inc."
COMPANY_ADDRESS = "301 Roycefield Rd., Hillsborough, NJ 08844"
COMPANY_PHONE   = "Tel: 908.526.4445  |  TF: 1.800.322.8823"
COMPANY_FAX     = "Fax: 908.526.9487  |  sales@gjsteel.com"
COMPANY_WEBSITE = "www.gjsteel.com"

PAGE_SIZE = landscape(letter)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE

MARGIN_H = 0.30 * inch
MARGIN_V = 0.22 * inch
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_H

FONT_TITLE = 16
FONT_SECTION = 10
FONT_BODY = 9
FONT_SMALL = 8
FONT_TINY = 7.5

GRID_WIDTH = 0.45
GRID_COLOR = colors.black

HEADER_BG = colors.HexColor("#D9ECFF")
SUBHEADER_BG = colors.HexColor("#EDF6FF")
LABEL_BG = colors.white
ROW_ALT_BG = colors.white

PASS_BG = colors.HexColor("#D9ECFF")
PASS_TEXT = colors.HexColor("#003875")
FAIL_BG = colors.HexColor("#B91C1C")
WARNING_BG = colors.HexColor("#FFF2CC")

PLACEHOLDER = "-"

CHEMICAL_ELEMENTS = [
    "C",
    "Mn",
    "S",
    "P",
    "Al",
    "Si",
    "N",
    "Cr",
    "Cu",
    "Ca",
    "Mo",
    "Ni",
]

MECHANICAL_PROPERTIES = [
    ("Tensile Strength", "certificate_tensile_strength", "tensile_strength"),
    ("Yield Strength", "certificate_yield_strength", "yield_strength"),
    ("Elongation", "certificate_elongation", "elongation"),
    ("Hardness", "certificate_hardness", "hardness"),
]

_MECH_SPEC_KEY_MAP = {
    "tensilestrength": "tensile_strength",
    "tensile": "tensile_strength",
    "uts": "tensile_strength",
    "ultimatetensilestrength": "tensile_strength",
    "yieldstrength": "yield_strength",
    "yield": "yield_strength",
    "ys": "yield_strength",
    "yield02": "yield_strength",
    "yield10": "yield_strength",
    "elongation": "elongation",
    "elong": "elongation",
    "hardness": "hardness",
    "hrb": "hardness",
    "hrc": "hardness",
    "rockwell": "hardness",
}


def _mech_spec_key(name):
    """Map a mechanical property display name to its required_mechanical_properties key."""
    token = re.sub(r"[^a-z0-9]+", "", _text(name).lower())
    if token in _MECH_SPEC_KEY_MAP:
        return _MECH_SPEC_KEY_MAP[token]
    for prefix, key in _MECH_SPEC_KEY_MAP.items():
        if token.startswith(prefix):
            return key
    return None


DEFAULT_INSTRUMENTS = {
    "OD": "Micrometer",
    "ID": "Micrometer",
    "Wall": "Micrometer",
    "Outside Diameter (OD)": "Micrometer",
    "Inner Diameter (ID)": "Micrometer",
    "Wall Thickness": "Micrometer",
    "Length": "Scale",
}


def _text(value, default=""):
    if value is None:
        return default

    text = str(value).strip()

    if not text or text.lower() in ("nan", "none", "null"):
        return default

    return text


def _cell(value, placeholder=PLACEHOLDER):
    return _text(value) or placeholder


def _fmt_measure(value):
    if value is None or value == "":
        return ""

    try:
        number = float(value)
        return f"{number:.5f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _mi(material_info, key, default=""):
    return _text(material_info.get(key, default), default)


def _po_number(material_info):
    for key in (
        "po_number",
        "po#",
        "po_no",
        "purchase_order",
        "certificate_purchase_order",
    ):
        value = _mi(material_info, key)

        if value:
            return value

    return ""


def _report_number(material_info):
    custom = _mi(material_info, "report_no")

    if custom:
        return custom

    part = _mi(material_info, "part_number") or _mi(material_info, "item_number")
    po = _po_number(material_info)

    if part and po:
        return f"IIR-{part}-{po}"

    if part:
        return f"IIR-{part}"

    return "IIR"


def _para(text, font_size=FONT_BODY, bold=False, align=TA_LEFT, color=None):
    style = ParagraphStyle(
        "DynamicPara",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=font_size,
        leading=font_size + 1.5,
        alignment=align,
        textColor=color or colors.black,
    )

    return Paragraph(_cell(text), style)


def _center(text, font_size=FONT_BODY, bold=False, color=None):
    return _para(text, font_size=font_size, bold=bold, align=TA_CENTER, color=color)


def _base_style(font_size=FONT_BODY, grid=True):
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    if grid:
        style.insert(0, ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR))

    return style


def _section_title(title):
    table = Table([[title]], colWidths=[CONTENT_WIDTH], rowHeights=[0.26 * inch])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR),
                ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), FONT_SECTION),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return table


def _resolve_logo_path(material_info):
    custom_logo = material_info.get("logo_path")

    if custom_logo:
        custom_logo = os.path.abspath(custom_logo)

        if os.path.isfile(custom_logo):
            return custom_logo

    if os.path.isfile(DEFAULT_LOGO_PATH):
        return DEFAULT_LOGO_PATH

    return None


def _logo_cell(material_info):
    logo_path = _resolve_logo_path(material_info)

    if not logo_path:
        return _center("G & J STEEL & TUBING, INC.", font_size=8, bold=True)

    image = Image(logo_path)
    max_width = 2.0 * inch
    max_height = 0.55 * inch
    aspect = image.imageWidth / float(image.imageHeight)
    image.drawWidth = max_width
    image.drawHeight = max_width / aspect

    if image.drawHeight > max_height:
        image.drawHeight = max_height
        image.drawWidth = max_height * aspect

    return image


def _build_company_block(width):
    """Logo and company name side by side, contact details below."""
    s_name = ParagraphStyle(
        "CName", fontName="Helvetica-Bold", fontSize=13, leading=15,
    )
    s_detail = ParagraphStyle(
        "CDetail", fontName="Helvetica", fontSize=7.5, leading=10,
        textColor=colors.HexColor("#333333"),
    )

    logo_w = 0.70 * inch
    name_w = width - logo_w

    # Row 0: logo | company name (side by side)
    logo_cell = ""
    if os.path.isfile(DEFAULT_LOGO_PATH):
        img = Image(DEFAULT_LOGO_PATH)
        max_h = 0.52 * inch
        aspect = img.imageWidth / float(img.imageHeight)
        img.drawHeight = max_h
        img.drawWidth  = max_h * aspect
        if img.drawWidth > logo_w:
            img.drawWidth  = logo_w
            img.drawHeight = logo_w / aspect
        logo_cell = img

    top_row = Table(
        [[logo_cell, Paragraph(COMPANY_NAME, s_name)]],
        colWidths=[logo_w, name_w],
    )
    top_row.setStyle(TableStyle([
        ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))

    # Details rows below
    details = Table(
        [
            [Paragraph(COMPANY_ADDRESS, s_detail)],
            [Paragraph(COMPANY_PHONE,   s_detail)],
            [Paragraph(COMPANY_FAX,     s_detail)],
            [Paragraph(COMPANY_WEBSITE, s_detail)],
        ],
        colWidths=[width],
    )
    details.setStyle(TableStyle([
        ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",   (0, 0), (-1, -1), 0.4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0.4),
    ]))

    outer = Table([[top_row], [details]], colWidths=[width])
    outer.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return outer


def _build_header_table(material_info):
    title = _center("CERTIFICATE TEST REPORT", font_size=FONT_TITLE, bold=True)

    company_w = 2.40 * inch
    col2_w    = 1.10 * inch
    col3_w    = 2.10 * inch
    col4_w    = 1.20 * inch
    col5_w    = CONTENT_WIDTH - company_w - col2_w - col3_w - col4_w

    data = [
        # Row 0: company block (spans all rows) | title (spans rows 0-1) | empty top-right
        [_build_company_block(company_w), "", title, "", "", ""],
        # Row 1: (spanned) | (spanned) | Inspection Date
        ["", "", "", "", _para("Inspection Date", bold=True),
         _para(_mi(material_info, "inspection_date"))],
        # Row 2: (spanned) | Supplier | PO
        ["", "", _para("Supplier", bold=True),
         _para(_mi(material_info, "supplier")),
         _para("PO No.", bold=True),
         _para(_po_number(material_info), bold=True)],
        # Row 3: (spanned) | Item / Part No. | Heat No.
        ["", "", _para("Item / Part No.", bold=True),
         _para(_mi(material_info, "item_number") or _mi(material_info, "part_number"), bold=True),
         _para("Heat No.", bold=True),
         _para(_mi(material_info, "heat_number"), bold=True)],
        # Row 4: (spanned) | Quantity
        ["", "", _para("Quantity", bold=True),
         _para(_mi(material_info, "quantity")),
         "", ""],
    ]

    widths = [1.40 * inch, 1.00 * inch, col2_w, col3_w, col4_w, col5_w]

    table = Table(
        data,
        colWidths=widths,
        rowHeights=[None, 0.27 * inch, 0.27 * inch, 0.27 * inch, 0.27 * inch],
    )
    table.setStyle(TableStyle(
        _base_style(FONT_BODY)
        + [
            ("SPAN",       (0, 0), (1, 4)),  # company block: cols 0-1, all 5 rows
            ("SPAN",       (2, 0), (3, 1)),  # title: cols 2-3, rows 0-1
            ("SPAN",       (4, 0), (5, 0)),  # empty top-right span
            ("VALIGN",     (0, 0), (1, 4), "TOP"),
            ("LEFTPADDING",  (0, 0), (1, 4), 0),
            ("TOPPADDING",   (0, 0), (1, 4), 0),
            ("RIGHTPADDING", (0, 0), (1, 4), 0),
            ("BOTTOMPADDING",(0, 0), (1, 4), 0),
            ("BACKGROUND", (2, 2), (2, 4), LABEL_BG),
            ("BACKGROUND", (4, 1), (4, 4), LABEL_BG),
        ]
    ))
    return table


def _first_nonempty(series):
    for value in series:
        text = _text(value)

        if text:
            return text

    return ""


def _instrument_for(measurement, material_info):
    instruments = material_info.get("instruments")

    if isinstance(instruments, dict) and measurement in instruments:
        return _text(instruments[measurement])

    keyed = material_info.get(f"instrument_{measurement}")

    if keyed:
        return _text(keyed)

    return DEFAULT_INSTRUMENTS.get(measurement, "")


def _status_style(style, row, column, status):
    status = _text(status).upper()

    if status == "PASS":
        style.append(("BACKGROUND", (column, row), (column, row), PASS_BG))
        style.append(("TEXTCOLOR", (column, row), (column, row), PASS_TEXT))
        style.append(("FONTNAME", (column, row), (column, row), "Helvetica-Bold"))
    elif status == "FAIL":
        style.append(("BACKGROUND", (column, row), (column, row), FAIL_BG))
        style.append(("TEXTCOLOR", (column, row), (column, row), colors.white))
        style.append(("FONTNAME", (column, row), (column, row), "Helvetica-Bold"))
    elif status:
        style.append(("BACKGROUND", (column, row), (column, row), WARNING_BG))
        style.append(("FONTNAME", (column, row), (column, row), "Helvetica-Bold"))


def _build_traceability_table(material_info):
    notes = _mi(material_info, "certificate_notes")

    data = [[
        _para("Reference Spec", bold=True),
        _para(_mi(material_info, "reference_specification"), bold=True),
        _para("Required Grade", bold=True),
        _para(_mi(material_info, "required_material_grade"), bold=True),
        _para("Review Notes", bold=True),
        _para(notes),
    ]]

    widths = [
        1.05 * inch,
        1.55 * inch,
        1.05 * inch,
        1.55 * inch,
        0.90 * inch,
        CONTENT_WIDTH - (1.05 + 1.55 + 1.05 + 1.55 + 0.90) * inch,
    ]
    table = Table(data, colWidths=widths)
    table.setStyle(TableStyle(
        _base_style(FONT_SMALL) + [
            ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
            ("BACKGROUND", (2, 0), (2, 0), LABEL_BG),
            ("BACKGROUND", (4, 0), (4, 0), LABEL_BG),
        ]
    ))
    return [table]


def _build_measurement_table(results_df, material_info):
    data = [
        [
            "No.",
            "Characteristic",
            "Specified",
            "Average",
            "Min",
            "Max",
            "Instrument",
            "Result",
        ]
    ]

    if results_df is None or results_df.empty:
        data.append(["", "", "", "", "", "", "", ""])
    else:
        for index, measurement in enumerate(results_df["measurement"].unique(), start=1):
            measurement_data = results_df[results_df["measurement"] == measurement]
            values = measurement_data["value"]
            lsl = measurement_data["lsl"].iloc[0]
            usl = measurement_data["usl"].iloc[0]
            min_value = (
                measurement_data["min"].min()
                if "min" in measurement_data.columns
                else values.min()
            )
            max_value = (
                measurement_data["max"].max()
                if "max" in measurement_data.columns
                else values.max()
            )
            instrument = (
                _first_nonempty(measurement_data["instrument"])
                if "instrument" in measurement_data.columns
                else ""
            )
            result = (
                "PASS"
                if all(measurement_data["result"] == "PASS")
                else "FAIL"
            )

            data.append(
                [
                    index,
                    measurement,
                    f"{_fmt_measure(lsl)} to {_fmt_measure(usl)}",
                    _fmt_measure(values.mean()),
                    _fmt_measure(min_value),
                    _fmt_measure(max_value),
                    instrument or _instrument_for(measurement, material_info),
                    result,
                ]
            )

    widths = [
        0.42 * inch,
        1.55 * inch,
        1.25 * inch,
        0.90 * inch,
        0.85 * inch,
        0.85 * inch,
        1.35 * inch,
        CONTENT_WIDTH - (0.42 + 1.55 + 1.25 + 0.90 + 0.85 + 0.85 + 1.35) * inch,
    ]
    table = Table(data, colWidths=widths)
    style = _base_style(FONT_BODY) + [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT_BG]),
    ]

    for row in range(1, len(data)):
        _status_style(style, row, 7, data[row][7])

    table.setStyle(TableStyle(style))
    return [_section_title("Dimensional Inspection Results"), table]


def _number_from_text(value):
    text = _text(value).replace(",", "")
    match = re.search(r"[-+]?\d*\.?\d+", text)

    if not match:
        return None

    return float(match.group())


def _limits_from_spec(specified):
    text = _text(specified).replace(",", "").strip()

    if not text:
        return None, None

    lower_text = text.lower()

    # Range pattern: "0.18-0.23" or "0.18 to 0.23"
    # Require each side to start with a digit so a hyphen is not mistaken for a negative sign.
    range_match = re.search(r"(\d[\d.]*)\s*(?:to|-)\s*(\d[\d.]*)", text)
    if range_match:
        a = float(range_match.group(1))
        b = float(range_match.group(2))
        return min(a, b), max(a, b)

    # Single value with a qualifier keyword
    number_match = re.search(r"[-+]?\d*\.?\d+", text)
    if not number_match:
        return None, None

    value = float(number_match.group())

    if "max" in lower_text or "<" in lower_text:
        return None, value

    if "min" in lower_text or ">" in lower_text:
        return value, None

    return None, None


def _result_from_spec(specified, observed):
    if not _text(observed):
        return ""

    if not _text(specified):
        return "REVIEW"

    observed_value = _number_from_text(observed)
    lower, upper = _limits_from_spec(specified)

    if observed_value is None or (lower is None and upper is None):
        return "REVIEW"

    if lower is not None and observed_value < lower:
        return "FAIL"

    if upper is not None and observed_value > upper:
        return "FAIL"

    return "PASS"


def _dict_value(data, key):
    if not isinstance(data, dict):
        return ""

    for candidate in (key, key.upper(), key.lower(), key.title()):
        if candidate in data:
            return _text(data.get(candidate))

    return ""


def _build_chemical_table(material_info):
    observed = material_info.get("chemical_composition", {})
    specified = material_info.get("required_chemical_properties", {})

    elements = [
        element
        for element in CHEMICAL_ELEMENTS
        if _dict_value(observed, element) or _dict_value(specified, element)
    ]

    if not elements:
        return []

    data = [
        ["Chemical Property"] + elements,
        ["Specified"] + [_cell(_dict_value(specified, element)) for element in elements],
        ["Observed"] + [_cell(_dict_value(observed, element)) for element in elements],
        [
            "Result"
        ]
        + [
            _result_from_spec(
                _dict_value(specified, element),
                _dict_value(observed, element),
            )
            for element in elements
        ],
    ]

    first_width = 0.95 * inch
    col_width = (CONTENT_WIDTH - first_width) / len(elements)
    table = Table(data, colWidths=[first_width] + [col_width] * len(elements))

    style = _base_style(FONT_TINY) + [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("BACKGROUND", (0, 1), (0, -1), LABEL_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]

    for column in range(1, len(elements) + 1):
        _status_style(style, 3, column, data[3][column])

    table.setStyle(TableStyle(style))
    return [_section_title("Chemical Properties"), table]


def _build_mechanical_table(material_info):
    specified = material_info.get("required_mechanical_properties", {})

    headers = [name for name, _, _ in MECHANICAL_PROPERTIES]
    specified_values = [
        _cell(_dict_value(specified, spec_key))
        for _, _, spec_key in MECHANICAL_PROPERTIES
    ]
    observed_values = [
        _cell(_mi(material_info, observed_key))
        for _, observed_key, _ in MECHANICAL_PROPERTIES
    ]
    result_values = [
        _result_from_spec(specified_values[index], observed_values[index])
        for index in range(len(headers))
    ]

    if all(value == PLACEHOLDER for value in observed_values + specified_values):
        return []

    data = [
        ["Mechanical Property"] + headers,
        ["Specified"] + specified_values,
        ["Observed"] + observed_values,
        ["Result"] + result_values,
    ]

    first_width = 1.10 * inch
    col_width = (CONTENT_WIDTH - first_width) / len(headers)
    table = Table(data, colWidths=[first_width] + [col_width] * len(headers))

    style = _base_style(FONT_SMALL) + [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("BACKGROUND", (0, 1), (0, -1), LABEL_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]

    for column in range(1, len(headers) + 1):
        _status_style(style, 3, column, data[3][column])

    table.setStyle(TableStyle(style))
    return [_section_title("Mechanical Properties"), table]


def _detect_unit(value_str):
    """Extract a unit abbreviation from a value string."""
    if not value_str:
        return ""
    s = str(value_str)
    for u in ["N/mm²", "N/mm2", "MPa", "ksi", "PSI", "HRB", "HRC", "HV", "HB"]:
        if u.lower() in s.lower():
            return u
    if "%" in s:
        return "%"
    return ""


_MECHANICAL_UNIT_PATTERN = r"N/mm(?:Â²|²|2)|MPa|ksi|PSI|HRB|HRC|HV|HB|%"


def _clean_mechanical_unit(value):
    unit = _text(value)
    if not unit:
        return ""

    normalized = unit.lower().replace(" ", "")
    if normalized.startswith("n/mm"):
        return "N/mm2"
    if normalized == "mpa":
        return "MPa"
    if normalized == "ksi":
        return "ksi"
    if normalized == "psi":
        return "PSI"
    if normalized in ("hrb", "hrc", "hv", "hb"):
        return normalized.upper()
    if normalized == "%":
        return "%"

    return unit


def _clean_mechanical_label(value):
    text = _text(value)
    if not text:
        return ""

    text = re.sub(
        rf"\s*\(\s*(?:{_MECHANICAL_UNIT_PATTERN})\s*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s+\b(?:min|max|minimum|maximum)\b\.?$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text.replace("_", " ")).strip()
    return text


def _format_mechanical_value(value):
    text = _text(value)
    if not text:
        return ""

    if text.lower() in ("n/a", "n.a", "n.s", "n.s.", "n.t", "n.t.", "not tested"):
        return text

    text = re.sub(rf"(?:{_MECHANICAL_UNIT_PATTERN})", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*/\s*", " / ", text)
    text = re.sub(r"\s+", " ", text).strip()

    def format_number(match):
        raw = match.group(0)
        try:
            number = float(raw.replace(",", ""))
        except ValueError:
            return raw

        if abs(number) < 1000:
            return raw

        if number.is_integer():
            return f"{int(number):,}"

        decimal_places = len(raw.split(".", 1)[1]) if "." in raw else 0
        return f"{number:,.{decimal_places}f}"

    return re.sub(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?", format_number, text)


def _build_combined_properties_table(material_info, results_df):
    """
    Single horizontal table combining Chemical + Mechanical + Dimensional,
    matching the supplier certificate layout.
    Columns are individual properties; rows are Specified / Observed / Result.
    """
    _ABSENT = {
        "",
        "-",
        "n.a",
        "n/a",
        "na",
        "n.s",
        "n.s.",
        "ns",
        "n.t",
        "n.t.",
        "nt",
        "not tested",
        "not applicable",
    }

    def _has_real_value(v):
        """True only when v is a genuine measurement (not N.A / N.S / empty)."""
        text = _text(v).lower()
        if text in _ABSENT:
            return False

        parts = [part.strip() for part in re.split(r"\s*/\s*", text) if part.strip()]
        return not (parts and all(part in _ABSENT for part in parts))

    show_dim = True

    # ── Chemical columns ──────────────────────────────────────────────────────
    # Columns driven solely by cert observed values — only elements the cert measured.
    chem_obs       = material_info.get("chemical_composition", {})
    cert_chem_spec = material_info.get("cert_chemical_specified", {})
    chem_cols = [
        e for e in CHEMICAL_ELEMENTS
        if _has_real_value(_dict_value(chem_obs, e))
    ]

    # ── Mechanical columns ────────────────────────────────────────────────────
    cert_mech_spec = material_info.get("cert_mechanical_specified", {})
    mech_defs = [
        ("Tensile\nStr.", "certificate_tensile_strength", "tensile_strength"),
        ("Yield\nStr.",   "certificate_yield_strength",  "yield_strength"),
        ("Elongation",    "certificate_elongation",       "elongation"),
        ("Hardness",      "certificate_hardness",         "hardness"),
    ]

    def _cert_specifies(v):
        """Cert explicitly requires this property (has a real spec or N.S — but NOT N.A)."""
        t = _text(v).upper()
        return bool(t) and t not in ("N.A", "N/A")

    # Show a mechanical column only when the cert specifies it (any value except N.A)
    # OR when the cert has a real observed measurement for it.
    cert_mech_rows = material_info.get("cert_mechanical_properties", [])
    if not cert_mech_rows:
        cert_mech_rows = material_info.get("certificate_mechanical_properties", [])

    mech_cols = []
    if isinstance(cert_mech_rows, list):
        for row in cert_mech_rows:
            if not isinstance(row, dict):
                continue

            name = _text(row.get("property") or row.get("name"))
            observed = _text(row.get("observed") or row.get("value"))
            specified = _text(row.get("specified") or row.get("spec"))
            unit = _text(row.get("unit") or row.get("units"))
            result = _text(row.get("result") or row.get("status"))

            if name and (observed or specified or unit):
                mech_cols.append({
                    "name": name,
                    "specified": specified,
                    "observed": observed,
                    "unit": unit,
                    "result": result,
                })

    if not mech_cols:
        mech_cols = [
            {
                "name": disp,
                "specified": _dict_value(cert_mech_spec, sk),
                "observed": _mi(material_info, ok),
                "unit": "",
                "result": "",
            }
            for disp, ok, sk in mech_defs
            if _has_real_value(_mi(material_info, ok))
        ]

    # ── Dimensional columns ───────────────────────────────────────────────────
    _CERT_DIM_MAP = {
        "OD":           "certificate_outside_diameter",
        "ID":           "certificate_inside_diameter",
        "Wall":         "certificate_wall_thickness",
        "Length":       "certificate_length",
        "Straightness": "certificate_straightness",
    }
    _CERT_DIM_SPEC_KEY = {
        "OD":           "outside_diameter",
        "ID":           "inside_diameter",
        "Wall":         "wall_thickness",
        "Length":       "length",
        "Straightness": "straightness",
    }

    required_dims = ["OD", "ID", "Wall", "Length", "Straightness"]

    # DB limits kept only for PASS/FAIL calculation; cert values drive display.
    dim_spec_lookup = {}
    for d in material_info.get("required_dimensional_limits", []):
        dim_spec_lookup[d.get("measurement", "")] = d

    cert_dim_spec = material_info.get("certificate_dimensional_specified", {})

    # Columns driven by cert observed OR cert dimensional_specified.
    dim_cols = []
    if show_dim:
        for dim_name in required_dims:
            cert_key      = _CERT_DIM_MAP.get(dim_name, "")
            obs_val       = _mi(material_info, cert_key) if cert_key else ""
            cert_spec_key = _CERT_DIM_SPEC_KEY.get(dim_name, "")
            cert_spec_val = _text(cert_dim_spec.get(cert_spec_key, "")) if cert_spec_key else ""

            # Only include when the cert has a numeric dimensional measurement
            # OR an explicit dimensional spec. Textual-only values like
            # "Satisfactory" coming from notes are not dimensional table data.
            has_numeric_obs = _has_real_value(obs_val) and _number_from_text(obs_val) is not None
            has_cert_spec   = _has_real_value(cert_spec_val)
            if not has_numeric_obs and not has_cert_spec:
                continue
            # If AI duplicated the spec value into the observed field, clear it.
            if obs_val and obs_val == cert_spec_val:
                obs_val = ""

            # DB limits used only for PASS/FAIL
            spec_d   = dim_spec_lookup.get(dim_name, {})
            lsl      = spec_d.get("lsl")
            usl      = spec_d.get("usl")
            has_real = (
                lsl is not None and usl is not None
                and not (lsl == 0 and usl == 0)
            )

            result = ""
            if _has_real_value(obs_val) and has_real:
                obs_num = _number_from_text(obs_val)
                if obs_num is not None:
                    result = "PASS" if lsl <= obs_num <= usl else "FAIL"

            dim_cols.append({
                "name": dim_name,
                "spec": cert_spec_val,
                "obs":  obs_val,
                "result": result,
                "lsl": lsl if has_real else None,
                "usl": usl if has_real else None,
            })

    n_c, n_m, n_d = len(chem_cols), len(mech_cols), len(dim_cols)
    n_total = n_c + n_m + n_d
    if n_total == 0:
        return []

    # ── Row 0: section header ─────────────────────────────────────────────────
    row0 = [""] * (1 + n_total)
    spans = []
    ci = 1
    if n_c:
        row0[ci] = "CHEMICAL PROPERTIES"
        if n_c > 1: spans.append((ci, ci + n_c - 1, 0))
        ci += n_c
    if n_m:
        row0[ci] = "MECHANICAL PROPERTIES"
        if n_m > 1: spans.append((ci, ci + n_m - 1, 0))
        ci += n_m
    if n_d:
        row0[ci] = "DIMENSIONAL PROPERTIES"
        if n_d > 1: spans.append((ci, ci + n_d - 1, 0))

    # ── Row 1: column headers with units ─────────────────────────────────────
    row1 = [_center("", FONT_TINY, bold=True)]
    for e in chem_cols:
        row1.append(_center(f"{e}\n(%)", FONT_TINY, bold=True))
    for mech in mech_cols:
        disp = _clean_mechanical_label(mech.get("name", ""))
        sv = mech.get("specified", "")
        ov = mech.get("observed", "")
        u = _clean_mechanical_unit(
            mech.get("unit", "")
            or _detect_unit(mech.get("name", ""))
            or _detect_unit(sv)
            or _detect_unit(ov)
        )
        row1.append(_center(f"{disp}\n({u})" if u else disp, FONT_TINY, bold=True))
    # Determine unit system from all observed/spec values: any value > 5 → metric (mm)
    _dim_nums = [
        _number_from_text(str(dd["obs"])) for dd in dim_cols
        if _text(dd["obs"]) and _text(dd["obs"]) not in ("N.A", "N.S", "N/A", "-")
    ] + [
        _number_from_text(str(dd["spec"])) for dd in dim_cols if _text(dd["spec"])
    ]
    _is_metric = any(n is not None and n > 5 for n in _dim_nums)
    _dim_unit  = "mm" if _is_metric else "in"

    for dd in dim_cols:
        row1.append(_center(f"{dd['name']}\n({_dim_unit})", FONT_TINY, bold=True))

    # ── Row 2: Specified — cert value preferred; DB spec used as fallback ────
    required_chem = material_info.get("required_chemical_properties", {})
    required_mech = material_info.get("required_mechanical_properties", {})
    row2 = [_para("Specified", FONT_SMALL, bold=True)]
    for e in chem_cols:
        spec_val = _dict_value(cert_chem_spec, e) or _dict_value(required_chem, e)
        row2.append(_center(_cell(spec_val), FONT_SMALL))
    for mech in mech_cols:
        spec_val = mech.get("specified", "")
        if not _text(spec_val):
            sk = _mech_spec_key(mech.get("name", ""))
            if sk:
                spec_val = _dict_value(required_mech, sk)
        row2.append(_center(_cell(_format_mechanical_value(spec_val)), FONT_SMALL))
    for dd in dim_cols:
        spec_val = dd["spec"]
        if not _text(spec_val):
            lsl_v, usl_v = dd.get("lsl"), dd.get("usl")
            if lsl_v is not None and usl_v is not None:
                spec_val = f"{_fmt_measure(lsl_v)} to {_fmt_measure(usl_v)}"
        row2.append(_center(_cell(spec_val), FONT_SMALL))

    # ── Row 3: Observed ───────────────────────────────────────────────────────
    heat = _mi(material_info, "heat_number")
    obs_lbl = f"Observed\n({heat})" if heat else "Observed"
    row3 = [_para(obs_lbl, FONT_SMALL, bold=True)]
    for e in chem_cols:
        row3.append(_center(_cell(_dict_value(chem_obs, e)), FONT_SMALL))
    for mech in mech_cols:
        row3.append(_center(_cell(_format_mechanical_value(mech.get("observed", ""))), FONT_SMALL))
    for dd in dim_cols:
        row3.append(_center(_cell(dd["obs"]), FONT_SMALL))

    data = [row0, row1, row2, row3]

    # ── Column widths ─────────────────────────────────────────────────────────
    label_w    = 0.80 * inch
    data_col_w = (CONTENT_WIDTH - label_w) / n_total
    col_widths = [label_w] + [data_col_w] * n_total

    table = Table(data, colWidths=col_widths)

    style = _base_style(FONT_SMALL) + [
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",      (0, 0), (0, -1),  "LEFT"),
        ("BACKGROUND", (0, 0), (-1, 0),  HEADER_BG),
        ("BACKGROUND", (0, 1), (-1, 1),  SUBHEADER_BG),
        ("BACKGROUND", (0, 0), (0, -1),  LABEL_BG),
        ("FONTNAME",   (0, 0), (-1, 1),  "Helvetica-Bold"),
        ("FONTNAME",   (0, 2), (0, -1),  "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 1),  FONT_TINY),
        ("ROWBACKGROUNDS", (1, 2), (-1, 3), [colors.white, ROW_ALT_BG]),
    ]
    for sc, ec, row in spans:
        style.append(("SPAN", (sc, row), (ec, row)))

    table.setStyle(TableStyle(style))
    return [_section_title("Material Properties Verification"), table]


def _build_remarks_table(material_info, final_result):
    """Certification remarks block matching the supplier certificate style."""
    accepted  = final_result == "LOT ACCEPTED"
    spec      = _mi(material_info, "reference_specification")
    grade     = _mi(material_info, "required_material_grade")
    supplier  = _mi(material_info, "supplier")
    heat      = _mi(material_info, "heat_number")

    spec_ref = f"{spec}, Grade {grade}" if grade else spec

    if accepted:
        remark = (
            f"This is to certify that the material supplied by {supplier} "
            f"(Heat No. {heat}) has been inspected and all tested values conform "
            f"to all requirements as per standard {spec_ref}. "
            f"The lot is accepted for use."
        ) if supplier and heat else (
            f"This is to certify that the material has been inspected and all tested "
            f"values conform to all requirements as per standard {spec_ref}."
        )
    else:
        remark = (
            f"This is to certify that the material supplied by {supplier} "
            f"(Heat No. {heat}) has been inspected. One or more tested values do not "
            f"conform to the requirements of standard {spec_ref}. "
            f"The lot is rejected."
        ) if supplier and heat else (
            f"This is to certify that the material has been inspected. One or more "
            f"tested values do not conform to the requirements of standard {spec_ref}. "
            f"The lot is rejected."
        )

    remark_style = ParagraphStyle(
        "RemarkStyle",
        fontName="Helvetica",
        fontSize=FONT_BODY,
        leading=FONT_BODY + 2,
        alignment=TA_LEFT,
        textColor=colors.black,
    )

    bg = PASS_BG if accepted else FAIL_BG
    txt_color = PASS_TEXT if accepted else colors.white

    label_style = ParagraphStyle(
        "RemarkLabel",
        fontName="Helvetica-Bold",
        fontSize=FONT_BODY,
        leading=FONT_BODY + 2,
        alignment=TA_LEFT,
        textColor=txt_color,
    )

    data = [[
        Paragraph("REMARKS", label_style),
        Paragraph(remark, remark_style),
    ]]

    label_w = 0.80 * inch
    table = Table(data, colWidths=[label_w, CONTENT_WIDTH - label_w], rowHeights=[0.72 * inch])
    table.setStyle(TableStyle([
        ("GRID",        (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",  (0, 0), (0, 0),   bg),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _build_inspection_summary_table(material_info, results_df):
    """
    Compact strip showing inspection sheet measured averages + inspector.
    Placed below the material properties table.
    """
    if results_df is None or results_df.empty:
        return []

    dims = []
    for meas in results_df["measurement"].unique():
        md  = results_df[results_df["measurement"] == meas]
        avg = md["value"].mean()
        dims.append((meas, _fmt_measure(avg)))

    if not dims:
        return []

    inspector   = _mi(material_info, "inspector") or "-"
    sample_size = _mi(material_info, "sample_size") or "-"

    # Fixed left columns: Inspected By | Sample Size | then one column per dim
    headers = [
        _center("Inspected By", FONT_SMALL, bold=True),
        _center("Sample Size", FONT_SMALL, bold=True),
    ] + [_center(f"{n}\nAvg.", FONT_SMALL, bold=True) for n, _ in dims]

    values = [
        _center(inspector, FONT_SMALL, bold=True),
        _center(sample_size, FONT_SMALL),
    ] + [_center(v, FONT_SMALL) for _, v in dims]

    n_cols   = len(headers)
    fixed_w  = 1.20 * inch
    dim_w    = (CONTENT_WIDTH - fixed_w * 2) / max(len(dims), 1)
    col_widths = [fixed_w, fixed_w] + [dim_w] * len(dims)

    table = Table([headers, values], colWidths=col_widths)
    table.setStyle(TableStyle(
        _base_style(FONT_SMALL) + [
            ("BACKGROUND", (0, 0), (-1, 0), SUBHEADER_BG),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 0), (0, 1),  LABEL_BG),
        ]
    ))
    return [_section_title("Incoming Inspection Results"), table]


def _build_conclusion_table(final_result):
    accepted = final_result == "LOT ACCEPTED"
    rejected = final_result == "LOT REJECTED"

    data = [
        [
            _para("Final Disposition", bold=True),
            _center("[X] Lot Accepted" if accepted else "[ ] Lot Accepted", bold=True),
            _center("[X] Lot Rejected" if rejected else "[ ] Lot Rejected", bold=True),
            _center("[ ] Concession Accepted", bold=True),
        ]
    ]

    col_width = CONTENT_WIDTH / 4.0
    table = Table(data, colWidths=[col_width] * 4, rowHeights=[0.36 * inch])
    style = _base_style(FONT_BODY) + [
        ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]

    if accepted:
        style.append(("BACKGROUND", (1, 0), (1, 0), PASS_BG))
        style.append(("TEXTCOLOR", (1, 0), (1, 0), PASS_TEXT))

    if rejected:
        style.append(("BACKGROUND", (2, 0), (2, 0), FAIL_BG))
        style.append(("TEXTCOLOR", (2, 0), (2, 0), colors.white))

    table.setStyle(TableStyle(style))
    return table


def _build_signature_table(material_info):
    """
    Professional three-column footer:
      Inspected By  |  Reviewed By  |  Official Stamp
    """
    inspector = _mi(material_info, "inspector")
    date      = _mi(material_info, "inspection_date")

    s_role = ParagraphStyle("SigRole", fontName="Helvetica-Bold",
        fontSize=FONT_SMALL, leading=FONT_SMALL + 2, alignment=TA_CENTER)
    s_name = ParagraphStyle("SigName", fontName="Helvetica",
        fontSize=FONT_SMALL, leading=FONT_SMALL + 2, alignment=TA_CENTER,
        textColor=colors.HexColor("#222222"))
    s_sub = ParagraphStyle("SigSub", fontName="Helvetica",
        fontSize=FONT_TINY, leading=FONT_TINY + 2, alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"))
    s_dept = ParagraphStyle("SigDept", fontName="Helvetica-Oblique",
        fontSize=FONT_TINY, leading=FONT_TINY + 2, alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"))
    s_stamp = ParagraphStyle("StampText", fontName="Helvetica",
        fontSize=FONT_SMALL, leading=FONT_SMALL + 2, alignment=TA_CENTER,
        textColor=colors.HexColor("#CCCCCC"))

    sig_line = "_" * 36
    col_w = CONTENT_WIDTH / 3.0
    inner_w = col_w - 0.16 * inch

    def _make_sig_block(role, name, dept):
        rows = [
            [Paragraph(role, s_role)],
            [Spacer(1, 3)],
            [Paragraph(sig_line, s_name)],
            [Paragraph(name, s_sub)],
            [Paragraph(dept, s_dept)],
        ]
        t = Table(rows, colWidths=[inner_w])
        t.setStyle(TableStyle([
            ("ALIGN",          (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING",    (0, 0), (-1, -1), 3),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 3),
            ("TOPPADDING",     (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 1),
        ]))
        return t

    date_note = f"Date: {date}" if date else ""
    insp_name = f"{inspector}   {date_note}".strip() if date_note else inspector

    insp_block  = _make_sig_block("Inspected By",  insp_name, "INCOMING INSPECTION DEPT.")
    review_block = _make_sig_block("Reviewed By",  "",         "QUALITY ASSURANCE DEPT.")

    stamp_t = Table(
        [[Paragraph("OFFICIAL STAMP", s_stamp)]],
        colWidths=[inner_w],
    )
    stamp_t.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))

    outer = Table(
        [[insp_block, review_block, stamp_t]],
        colWidths=[col_w] * 3,
        rowHeights=[1.40 * inch],
    )
    outer.setStyle(TableStyle([
        ("GRID",       (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (2, 0), (2,  0),  colors.HexColor("#F8F8F8")),
    ]))
    return outer


def _build_ai_certification_note():
    note = (
        "This certificate test report was generated by AI based on the G & J "
        "incoming inspection process and the supplier material test certificate."
    )

    style = ParagraphStyle(
        "AICertificationNote",
        fontName="Helvetica-Oblique",
        fontSize=FONT_TINY,
        leading=FONT_TINY + 2,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
    )

    table = Table([[Paragraph(note, style)]], colWidths=[CONTENT_WIDTH])
    table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return table


def create_inspection_pdf(
    output_path,
    material_info,
    results_df,
    summary_df,
    final_result,
):
    """
    Build the Incoming Inspection Report PDF.

    summary_df is accepted for compatibility with older callers.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=MARGIN_V,
        bottomMargin=MARGIN_V,
        title="Incoming Inspection Report",
    )

    footer_style = ParagraphStyle(
        "FooterStyle",
        fontName="Helvetica-Oblique",
        fontSize=FONT_TINY,
        leading=FONT_TINY + 1,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#555555"),
    )

    story = [
        _build_header_table(material_info),
        Spacer(1, 6),
    ]

    for table in _build_traceability_table(material_info):
        story.append(table)

    story.append(Spacer(1, 6))

    combined = _build_combined_properties_table(material_info, results_df)
    for table in combined:
        story.append(table)

    inspection_summary = _build_inspection_summary_table(material_info, results_df)
    if inspection_summary:
        story.append(Spacer(1, 6))
        for table in inspection_summary:
            story.append(table)

    story.extend(
        [
            Spacer(1, 6),
            _build_remarks_table(material_info, final_result),
            Spacer(1, 6),
            _build_conclusion_table(final_result),
            Spacer(1, 6),
            _build_signature_table(material_info),
            Spacer(1, 4),
            _build_ai_certification_note(),
        ]
    )

    doc.build(story)
