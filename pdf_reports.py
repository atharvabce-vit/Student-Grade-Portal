"""Batch report cards as a single PDF (one page per student)."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _card_flowables(row, details, subjects, max_mark, pass_mark, grade_of, result_of, attendance_rate=None):
    rows = list(row[2:2 + len(subjects)])
    total = sum(rows)
    maximum = len(subjects) * max_mark
    percentage = total / maximum * 100 if maximum else 0
    grade = grade_of(percentage)
    result = result_of(rows)

    styles = getSampleStyleSheet()
    title = ParagraphStyle("CardTitle", parent=styles["Title"], fontSize=16, spaceAfter=6)
    normal = styles["Normal"]

    flowables = [
        Paragraph("Report Card", title),
        Paragraph(f"<b>{row[1]}</b> &nbsp;&nbsp; Reg No: {row[0]}", normal),
    ]

    detail_bits = [
        f"{key.replace('_', ' ').title()}: {details.get(key)}"
        for key in ("student_class", "section", "academic_year", "term", "guardian")
        if details and details.get(key)
    ]
    if detail_bits:
        flowables.append(Paragraph(" &nbsp;|&nbsp; ".join(detail_bits), normal))

    if attendance_rate is not None:
        flowables.append(Paragraph(f"Attendance: {attendance_rate:.1f}%", normal))

    flowables.append(Spacer(1, 8))

    data = [["Subject", "Marks", "Out of", "Status"]]
    for index, subject in enumerate(subjects):
        mark = rows[index] if index < len(rows) else 0
        data.append([subject, str(mark), str(max_mark), "Pass" if mark >= pass_mark else "Fail"])

    table = Table(data, hAlign="LEFT", colWidths=[70 * mm, 30 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    flowables.append(table)

    flowables.append(Spacer(1, 10))
    summary = Table(
        [
            ["Total", str(total)],
            ["Percentage", f"{percentage:.2f}%"],
            ["Grade", grade],
            ["Result", result],
        ],
        hAlign="LEFT",
        colWidths=[40 * mm, 40 * mm],
    )
    summary.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    flowables.append(summary)
    return flowables


def build_report_cards_bytes(rows, details_map, subjects, max_mark, pass_mark, grade_of, result_of):
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title="Student Report Cards",
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    flowables = []
    for index, row in enumerate(rows):
        if index > 0:
            flowables.append(PageBreak())
        flowables.extend(
            _card_flowables(
                row,
                details_map.get(row[0], {}),
                subjects,
                max_mark,
                pass_mark,
                grade_of,
                result_of,
            )
        )

    if not flowables:
        flowables = [Paragraph("No students to export.", getSampleStyleSheet()["Normal"])]

    document.build(flowables)
    return buffer.getvalue()


_GRID_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ("FONTSIZE", (0, 0), (-1, -1), 10),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
])


def build_transcript_pdf(student, details, terms, overall, exams, max_mark):
    """One-student academic transcript with a table per term."""
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TTitle", parent=styles["Title"], fontSize=16, spaceAfter=6)
    heading = styles["Heading3"]
    normal = styles["Normal"]

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Transcript - {student['name']}",
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    flowables = [
        Paragraph("Academic Transcript", title),
        Paragraph(f"<b>{student['name']}</b> &nbsp;&nbsp; Reg No: {student['reg_no']}", normal),
    ]

    detail_bits = [
        f"{key.replace('_', ' ').title()}: {details.get(key)}"
        for key in ("student_class", "section", "academic_year", "guardian")
        if details and details.get(key)
    ]
    if detail_bits:
        flowables.append(Paragraph(" &nbsp;|&nbsp; ".join(detail_bits), normal))
    flowables.append(Spacer(1, 10))

    if not terms:
        flowables.append(Paragraph("No term marks recorded for this student.", normal))
    else:
        for term in terms:
            flowables.append(Paragraph(term["term"], heading))
            header = ["Subject"] + list(exams) + ["Total"]
            data = [header]
            for row in term["rows"]:
                cells = [row["subject"]]
                cells += [
                    str(row["marks"][exam]) if row["marks"][exam] is not None else "-"
                    for exam in exams
                ]
                cells.append(str(sum(v for v in row["marks"].values() if v is not None)))
                data.append(cells)

            table = Table(data, hAlign="LEFT")
            table.setStyle(_GRID_STYLE)
            flowables.append(table)
            flowables.append(Spacer(1, 4))
            flowables.append(Paragraph(
                f"Term total: {term['earned']} / {term['maximum']} &nbsp;|&nbsp; "
                f"Percentage: {term['percentage']:.2f}% &nbsp;|&nbsp; Grade: {term['grade']}",
                normal,
            ))
            flowables.append(Spacer(1, 10))

    overall_table = Table(
        [
            ["Overall percentage", f"{overall['percentage']:.2f}%"],
            ["Overall grade", overall["grade"]],
        ],
        hAlign="LEFT",
        colWidths=[45 * mm, 45 * mm],
    )
    overall_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    flowables.append(Spacer(1, 6))
    flowables.append(overall_table)

    document.build(flowables)
    return buffer.getvalue()
