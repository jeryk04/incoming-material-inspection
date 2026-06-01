"""
Clean Incoming Inspection Report PDF generator.

This report shows:
- Header / material traceability
- Measurement average summary only
- AI supplier certificate review
- Final lot decision
- Inspector signature
"""

import os

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

# ==========================================================
# Paths
# ==========================================================

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_LOGO_PATH = os.path.join(_PROJECT_ROOT, "assets", "company_logo.png")

# ==========================================================
# Page Setup
# ==========================================================

PAGE_SIZE = landscape(letter)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE

MARGIN_H = 0.45 * inch
MARGIN_V = 0.35 * inch
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_H

# ==========================================================
# Fonts / Colors
# ==========================================================

FONT_BODY = 7.5
FONT_LABEL = 7
FONT_HEADER = 8
FONT_TITLE = 14
FONT_META = 7.5
FONT_NOTE = 6.4

GRID_WIDTH = 0.35
GRID_COLOR = colors.HexColor("#2F2F2F")

HEADER_BG = colors.HexColor("#D9D9D9")
LABEL_BG = colors.HexColor("#EFEFEF")
META_BG = colors.HexColor("#F5F5F5")
ROW_ALT_BG = colors.HexColor("#FAFAFA")

LOGO_BG = colors.black

PASS_BG = colors.HexColor("#E8F5E9")
PASS_TEXT = colors.HexColor("#1B5E20")

FAIL_BG = colors.HexColor("#B91C1C")
WARNING_BG = colors.HexColor("#FFF2CC")

PLACEHOLDER = "—"

NOTE_FOOTER = "Generated automatically from incoming inspection data and supplier certificate review."

_DEFAULT_INSTRUMENTS = {
    "OD": "Micrometer",
    "ID": "Micrometer",
    "Wall": "Micrometer",
    "Length": "Scale",
    "Width": "Scale",
    "Height": "Scale",
}


# ==========================================================
# Helpers
# ==========================================================

def _text(value, default=""):
    """Return a clean string for PDF display."""
    if value is None:
        return default

    text = str(value).strip()

    if not text or text.lower() in ("nan", "none", "null"):
        return default

    return text


def _cell(value, placeholder=PLACEHOLDER):
    """Return placeholder when value is empty."""
    value = _text(value)

    if value:
        return value

    return placeholder


def _fmt_measure(value):
    """Format measurement values cleanly."""
    if value is None or value == "":
        return ""

    try:
        number = float(value)
        return f"{number:.5f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _mi(material_info, key, default=""):
    """Shortcut for material_info lookup."""
    return _text(material_info.get(key, default), default)


def _po_number(material_info):
    """Get PO number from possible keys."""
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
    """Return report number."""
    custom = _mi(material_info, "report_no")

    if custom:
        return custom

    part = _mi(material_info, "part_number")
    po = _po_number(material_info)

    if part and po:
        return f"IIR-{part}-{po}"

    if part:
        return f"IIR-{part}"

    return "IIR"


def _base_table_style(font_size=FONT_BODY, grid=True):
    """Common table style."""
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    if grid:
        style.insert(0, ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR))

    return style


def _label_para(text):
    """Formatted label paragraph."""
    style = ParagraphStyle(
        "LabelStyle",
        fontName="Helvetica-Bold",
        fontSize=FONT_LABEL,
        leading=FONT_LABEL + 1,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#111111"),
    )

    return Paragraph(str(text), style)


def _value_para(value, bold=False):
    """Formatted value paragraph."""
    style = ParagraphStyle(
        "ValueStyle",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=FONT_META,
        leading=FONT_META + 1,
        alignment=TA_LEFT,
    )

    return Paragraph(_cell(value), style)


def _small_value_para(value, bold=False):
    """Smaller value paragraph."""
    style = ParagraphStyle(
        "SmallValueStyle",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=FONT_NOTE,
        leading=FONT_NOTE + 1,
        alignment=TA_LEFT,
    )

    return Paragraph(_cell(value), style)


def _center_para(text, font_size=FONT_BODY, bold=False):
    """Centered paragraph."""
    style = ParagraphStyle(
        "CenterStyle",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=font_size,
        leading=font_size + 1,
        alignment=TA_CENTER,
    )

    return Paragraph(str(text), style)


# ==========================================================
# Logo
# ==========================================================

def _resolve_logo_path(material_info):
    """Return valid logo path if available."""
    custom_logo = material_info.get("logo_path")

    if custom_logo:
        custom_logo = os.path.abspath(custom_logo)

        if os.path.isfile(custom_logo):
            return custom_logo

    if os.path.isfile(DEFAULT_LOGO_PATH):
        return DEFAULT_LOGO_PATH

    return None


def _build_logo_image(logo_path):
    """Scale logo for header."""
    max_width = 2.25 * inch
    max_height = 0.75 * inch

    image = Image(logo_path)

    aspect = image.imageWidth / float(image.imageHeight)
    image.drawWidth = max_width
    image.drawHeight = max_width / aspect

    if image.drawHeight > max_height:
        image.drawHeight = max_height
        image.drawWidth = max_height * aspect

    return image


def _header_logo_cell(material_info):
    """Return logo or text fallback."""
    logo_path = _resolve_logo_path(material_info)

    if logo_path:
        return _build_logo_image(logo_path)

    return _center_para("G & J STEEL & TUBING, INC.", font_size=8, bold=True)


# ==========================================================
# Header Table
# ==========================================================

def _build_header_table(material_info):
    """Build top report header."""
    col_w = CONTENT_WIDTH / 12.0
    col_widths = [col_w] * 12

    title_style = ParagraphStyle(
        "ReportTitle",
        fontName="Helvetica-Bold",
        fontSize=FONT_TITLE,
        leading=FONT_TITLE + 2,
        alignment=TA_CENTER,
    )

    title = Paragraph("Incoming Inspection Report", title_style)

    quantity = _mi(material_info, "quantity") or _mi(material_info, "lot_qty")
    item_number = _mi(material_info, "item_number") or _mi(material_info, "part_number")

    header_data = [
        [
            _header_logo_cell(material_info),
            "",
            "",
            "",
            title,
            "",
            "",
            "",
            _label_para("Date"),
            _value_para(_mi(material_info, "inspection_date")),
            "",
            "",
        ],
        [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            _label_para("Report No."),
            _value_para(_report_number(material_info), bold=True),
            "",
            "",
        ],
        [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            _label_para("Sample Size"),
            _value_para(_mi(material_info, "sample_size", "10")),
            "",
            "",
        ],
        [
            _label_para("Supplier"),
            _value_para(_mi(material_info, "supplier")),
            "",
            "",
            _label_para("Item / Part #"),
            _value_para(item_number, bold=True),
            _label_para("PO #"),
            _value_para(_po_number(material_info), bold=True),
            _label_para("Quantity"),
            _value_para(quantity),
            _label_para("Heat No."),
            _value_para(_mi(material_info, "heat_number"), bold=True),
        ],
    ]

    table = Table(header_data, colWidths=col_widths)

    table.setStyle(
        TableStyle(
            _base_table_style(FONT_LABEL)
            + [
                ("SPAN", (0, 0), (3, 2)),
                ("BACKGROUND", (0, 0), (3, 2), LOGO_BG),
                ("ALIGN", (0, 0), (3, 2), "CENTER"),
                ("VALIGN", (0, 0), (3, 2), "MIDDLE"),

                ("SPAN", (4, 0), (7, 2)),
                ("ALIGN", (4, 0), (7, 2), "CENTER"),
                ("VALIGN", (4, 0), (7, 2), "MIDDLE"),

                ("SPAN", (9, 0), (11, 0)),
                ("SPAN", (9, 1), (11, 1)),
                ("SPAN", (9, 2), (11, 2)),

                ("SPAN", (1, 3), (3, 3)),

                ("BACKGROUND", (8, 0), (11, 2), META_BG),
                ("BACKGROUND", (0, 3), (0, 3), LABEL_BG),
                ("BACKGROUND", (4, 3), (4, 3), LABEL_BG),
                ("BACKGROUND", (6, 3), (6, 3), LABEL_BG),
                ("BACKGROUND", (8, 3), (8, 3), LABEL_BG),
                ("BACKGROUND", (10, 3), (10, 3), LABEL_BG),
            ]
        )
    )

    return table


# ==========================================================
# Measurement Summary
# ==========================================================

def _instrument_for(measurement, material_info):
    """Resolve measuring instrument."""
    instruments = material_info.get("instruments")

    if isinstance(instruments, dict) and measurement in instruments:
        return _text(instruments[measurement])

    keyed = material_info.get(f"instrument_{measurement}")

    if keyed:
        return _text(keyed)

    return _DEFAULT_INSTRUMENTS.get(measurement, "")


def _build_measurement_summary_table(results_df, material_info):
    """
    Build simplified measurement summary table.

    Shows only:
    characteristic, specification, average, min, max, instrument, result.
    """
    title_table = Table(
        [["Inspection Measurement Summary"]],
        colWidths=[CONTENT_WIDTH],
        rowHeights=[0.28 * inch],
    )

    title_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR),
                ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), FONT_HEADER),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    table_data = [
        [
            "Sl No",
            "Characteristic",
            "Specification",
            "Average",
            "Min",
            "Max",
            "Instrument Used",
            "Result",
        ]
    ]

    if results_df is None or results_df.empty:
        table_data.append(["", "", "", "", "", "", "", ""])
    else:
        sl_no = 1

        for measurement in results_df["measurement"].unique():
            measurement_data = results_df[results_df["measurement"] == measurement]

            values = measurement_data["value"]
            lsl = measurement_data["lsl"].iloc[0]
            usl = measurement_data["usl"].iloc[0]

            average_value = values.mean()
            min_value = values.min()
            max_value = values.max()

            result = (
                "PASS"
                if all(measurement_data["result"] == "PASS")
                else "FAIL"
            )

            table_data.append(
                [
                    sl_no,
                    measurement,
                    f"{_fmt_measure(lsl)} to {_fmt_measure(usl)}",
                    _fmt_measure(average_value),
                    _fmt_measure(min_value),
                    _fmt_measure(max_value),
                    _instrument_for(measurement, material_info),
                    result,
                ]
            )

            sl_no += 1

    while len(table_data) < 4:
        table_data.append(["", "", "", "", "", "", "", ""])

    col_widths = [
        0.55 * inch,
        1.25 * inch,
        1.40 * inch,
        1.15 * inch,
        1.00 * inch,
        1.00 * inch,
        1.55 * inch,
        CONTENT_WIDTH
        - (
            0.55 * inch
            + 1.25 * inch
            + 1.40 * inch
            + 1.15 * inch
            + 1.00 * inch
            + 1.00 * inch
            + 1.55 * inch
        ),
    ]

    table = Table(
        table_data,
        colWidths=col_widths,
        rowHeights=[0.34 * inch] + [0.32 * inch] * (len(table_data) - 1),
    )

    style = _base_table_style(FONT_BODY) + [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT_BG]),
    ]

    for row_index in range(1, len(table_data)):
        result_value = table_data[row_index][7]

        if result_value == "PASS":
            style.append(("BACKGROUND", (7, row_index), (7, row_index), PASS_BG))
            style.append(("TEXTCOLOR", (7, row_index), (7, row_index), PASS_TEXT))
            style.append(("FONTNAME", (7, row_index), (7, row_index), "Helvetica-Bold"))

        elif result_value == "FAIL":
            style.append(("BACKGROUND", (0, row_index), (-1, row_index), FAIL_BG))
            style.append(("TEXTCOLOR", (0, row_index), (-1, row_index), colors.white))
            style.append(("FONTNAME", (7, row_index), (7, row_index), "Helvetica-Bold"))

    table.setStyle(TableStyle(style))

    return [title_table, table]


# ==========================================================
# AI Certificate Review
# ==========================================================

def _build_certificate_review_table(material_info):
    """
    Build clean certificate review section.
    """
    heat_match = _mi(material_info, "certificate_heat_match", "REVIEW")
    certificate_result = _mi(
        material_info,
        "certificate_review_result",
        _mi(material_info, "certificate_review_status", "Reviewed"),
    )

    title_table = Table(
        [["AI Supplier Certificate Review"]],
        colWidths=[CONTENT_WIDTH],
        rowHeights=[0.28 * inch],
    )

    title_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR),
                ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), FONT_HEADER),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    review_data = [
        [
            _label_para("Cert Supplier"),
            _small_value_para(_mi(material_info, "certificate_supplier")),
            _label_para("Cert Heat No."),
            _small_value_para(_mi(material_info, "certificate_heat_number"), bold=True),
            _label_para("Excel Heat No."),
            _small_value_para(_mi(material_info, "heat_number"), bold=True),
            _label_para("Heat Match"),
            _small_value_para(heat_match, bold=True),
        ],
        [
            _label_para("Material"),
            _small_value_para(_mi(material_info, "certificate_material")),
            _label_para("Grade"),
            _small_value_para(_mi(material_info, "certificate_material_grade")),
            _label_para("Yield Strength"),
            _small_value_para(_mi(material_info, "certificate_yield_strength")),
            _label_para("Tensile Strength"),
            _small_value_para(_mi(material_info, "certificate_tensile_strength")),
        ],
        [
            _label_para("Elongation"),
            _small_value_para(_mi(material_info, "certificate_elongation")),
            _label_para("Hardness"),
            _small_value_para(_mi(material_info, "certificate_hardness")),
            _label_para("Certificate Result"),
            _small_value_para(certificate_result, bold=True),
            "",
            "",
        ],
    ]

    review_table = Table(
        review_data,
        colWidths=[
            0.90 * inch,
            1.35 * inch,
            0.90 * inch,
            1.20 * inch,
            1.00 * inch,
            1.20 * inch,
            1.10 * inch,
            CONTENT_WIDTH
            - (
                0.90 * inch
                + 1.35 * inch
                + 0.90 * inch
                + 1.20 * inch
                + 1.00 * inch
                + 1.20 * inch
                + 1.10 * inch
            ),
        ],
        rowHeights=[0.32 * inch, 0.34 * inch, 0.34 * inch],
    )

    style = _base_table_style(FONT_NOTE) + [
        ("BACKGROUND", (0, 0), (0, -1), LABEL_BG),
        ("BACKGROUND", (2, 0), (2, -1), LABEL_BG),
        ("BACKGROUND", (4, 0), (4, -1), LABEL_BG),
        ("BACKGROUND", (6, 0), (6, -1), LABEL_BG),
        ("SPAN", (5, 2), (7, 2)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    if heat_match == "PASS":
        style.append(("BACKGROUND", (7, 0), (7, 0), PASS_BG))
        style.append(("TEXTCOLOR", (7, 0), (7, 0), PASS_TEXT))
        style.append(("FONTNAME", (7, 0), (7, 0), "Helvetica-Bold"))
    else:
        style.append(("BACKGROUND", (7, 0), (7, 0), WARNING_BG))
        style.append(("FONTNAME", (7, 0), (7, 0), "Helvetica-Bold"))

    review_table.setStyle(TableStyle(style))

    return [title_table, review_table]


# ==========================================================
# Chemical Composition
# ==========================================================

def _build_chemical_composition_table(material_info):
    """Build chemical composition row from certificate data. Returns None if no data."""
    chem = material_info.get("chemical_composition", {})

    if not isinstance(chem, dict):
        return None

    elements = [(k, _text(v)) for k, v in chem.items() if _text(v)]

    if not elements:
        return None

    title_table = Table(
        [["Chemical Composition"]],
        colWidths=[CONTENT_WIDTH],
        rowHeights=[0.22 * inch],
    )

    title_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID_COLOR),
                ("BACKGROUND", (0, 0), (-1, -1), LABEL_BG),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), FONT_NOTE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    n = len(elements)
    col_w = CONTENT_WIDTH / n

    header_row = [_center_para(k, font_size=FONT_NOTE, bold=True) for k, _ in elements]
    value_row = [_center_para(v, font_size=FONT_NOTE) for _, v in elements]

    chem_table = Table(
        [header_row, value_row],
        colWidths=[col_w] * n,
        rowHeights=[0.24 * inch, 0.26 * inch],
    )

    chem_table.setStyle(
        TableStyle(
            _base_table_style(FONT_NOTE)
            + [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    return [title_table, chem_table]


# ==========================================================
# Certificate Notes
# ==========================================================

def _build_certificate_notes_table(material_info):
    """Build certificate test notes row. Returns None if no notes."""
    notes = _text(material_info.get("certificate_notes", ""))

    if not notes:
        return None

    notes_style = ParagraphStyle(
        "NotesStyle",
        fontName="Helvetica",
        fontSize=FONT_NOTE,
        leading=FONT_NOTE + 2,
        alignment=TA_LEFT,
    )

    data = [[_label_para("Certificate Notes"), Paragraph(notes, notes_style)]]

    col_widths = [1.10 * inch, CONTENT_WIDTH - 1.10 * inch]

    table = Table(data, colWidths=col_widths)

    table.setStyle(
        TableStyle(
            _base_table_style(FONT_NOTE)
            + [
                ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    return table


# ==========================================================
# Conclusion / Signature
# ==========================================================

def _build_conclusion_table(final_result):
    """Build lot decision row."""
    accepted = final_result == "LOT ACCEPTED"
    rejected = final_result == "LOT REJECTED"

    data = [
        [
            _label_para("Conclusion"),
            f"{'[X]' if accepted else '[ ]'} Lot Accepted",
            f"{'[X]' if rejected else '[ ]'} Lot Rejected",
            "[ ] Concession Accepted",
        ]
    ]

    col_width = CONTENT_WIDTH / 4.0

    table = Table(data, colWidths=[col_width] * 4, rowHeights=[0.30 * inch])

    style = _base_table_style(FONT_BODY) + [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
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
    """Build simple inspector signature row."""
    inspector = _mi(material_info, "inspector")
    inspection_date = _mi(material_info, "inspection_date")

    data = [
        [
            _label_para("Inspected by"),
            _value_para(inspector, bold=True),
            _label_para("Signature"),
            "",
            _label_para("Date"),
            _value_para(inspection_date),
        ]
    ]

    table = Table(
        data,
        colWidths=[
            1.00 * inch,
            1.35 * inch,
            1.00 * inch,
            4.20 * inch,
            0.75 * inch,
            CONTENT_WIDTH
            - (
                1.00 * inch
                + 1.35 * inch
                + 1.00 * inch
                + 4.20 * inch
                + 0.75 * inch
            ),
        ],
        rowHeights=[0.34 * inch],
    )

    table.setStyle(
        TableStyle(
            _base_table_style(FONT_BODY)
            + [
                ("BACKGROUND", (0, 0), (0, 0), LABEL_BG),
                ("BACKGROUND", (2, 0), (2, 0), LABEL_BG),
                ("BACKGROUND", (4, 0), (4, 0), LABEL_BG),
            ]
        )
    )

    return table


# ==========================================================
# Main PDF Function
# ==========================================================

def create_inspection_pdf(
    output_path,
    material_info,
    results_df,
    summary_df,
    final_result,
):
    """
    Build landscape Incoming Inspection Report PDF.

    summary_df is kept in the function signature for compatibility,
    but Cp/Cpk summary is intentionally not displayed.
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
        fontSize=FONT_NOTE,
        leading=FONT_NOTE + 1,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#555555"),
    )

    story = []

    story.append(_build_header_table(material_info))
    story.append(Spacer(1, 8))

    for table in _build_measurement_summary_table(results_df, material_info):
        story.append(table)

    story.append(Spacer(1, 8))

    for table in _build_certificate_review_table(material_info):
        story.append(table)

    chem_tables = _build_chemical_composition_table(material_info)
    if chem_tables:
        story.append(Spacer(1, 4))
        for table in chem_tables:
            story.append(table)

    notes_table = _build_certificate_notes_table(material_info)
    if notes_table:
        story.append(Spacer(1, 4))
        story.append(notes_table)

    story.append(Spacer(1, 8))

    story.append(_build_conclusion_table(final_result))
    story.append(Spacer(1, 6))

    story.append(_build_signature_table(material_info))
    story.append(Spacer(1, 6))

    story.append(Paragraph(NOTE_FOOTER, footer_style))

    doc.build(story)