---
name: pdf-creation
description: Create polished custom PDF documents locally with ReportLab, including flowing multipage layouts, tables, images, fonts, headers, and footers. Use when generating or revising a PDF where visual layout must be rendered and verified before delivery.
---

# Local PDF creation

Create the PDF entirely on the local machine. Do not upload source material or the finished
document to a conversion service. Preserve the owner's source files and write a new output.

## Establish the artifact

Before coding, identify the page size, audience, content hierarchy, brand colors or fonts,
and final filename from the request and available files. When details are absent, use a
restrained document system: Letter or A4 as context suggests, 0.65-0.8 inch margins, one
body typeface, one heading family, and a small color palette with strong contrast.

Inspect the local toolchain:

```bash
python3 -c 'import reportlab; print(reportlab.Version)'
command -v pdftoppm
command -v pdfinfo
```

If a required dependency is absent, say exactly which one is missing and ask before changing
the machine. Typical dependencies are the `reportlab` Python package and Poppler's
`pdftoppm`/`pdfinfo` commands.

Keep working files in a task-specific temporary directory. Put the final PDF in the requested
location with a stable, descriptive name.

## Choose the right ReportLab layer

- Use Platypus (`SimpleDocTemplate`, `Paragraph`, `Table`, `Image`, and other flowables) for
  reports, proposals, invoices, handbooks, and documents whose content flows across pages.
- Use `BaseDocTemplate`, `PageTemplate`, and `Frame` when pages need distinct regions,
  repeating sidebars, or different first/continuation layouts.
- Use `canvas.Canvas` for fixed-coordinate pieces such as labels, certificates, tickets,
  diagrams, or overlays. Do not manually position an ordinary multipage report line by line.

Build reusable style and drawing functions rather than scattering coordinates, colors, and
font sizes through the script.

## Start from a robust flowing document

```python
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


PAGE_WIDTH, PAGE_HEIGHT = LETTER
MARGIN = 0.72 * inch

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="DocumentTitle",
    parent=styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=24,
    leading=29,
    spaceAfter=18,
    textColor=colors.HexColor("#17324D"),
    alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="BodyCopy",
    parent=styles["BodyText"],
    fontName="Helvetica",
    fontSize=10,
    leading=14,
    spaceAfter=8,
    textColor=colors.HexColor("#24313D"),
))


def decorate_page(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7DEE5"))
    canvas.line(MARGIN, 0.55 * inch, PAGE_WIDTH - MARGIN, 0.55 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#66717C"))
    canvas.drawRightString(
        PAGE_WIDTH - MARGIN,
        0.35 * inch,
        f"Page {document.page}",
    )
    canvas.restoreState()


document = SimpleDocTemplate(
    "custom-report.pdf",
    pagesize=LETTER,
    leftMargin=MARGIN,
    rightMargin=MARGIN,
    topMargin=0.75 * inch,
    bottomMargin=0.72 * inch,
    title="Custom report",
    author="",
)

story = [
    Paragraph("Custom report", styles["DocumentTitle"]),
    KeepTogether([
        Paragraph("Section heading", styles["Heading2"]),
        Paragraph("Content that stays with its heading.", styles["BodyCopy"]),
    ]),
    Spacer(1, 8),
]

document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
```

Treat all text inserted into `Paragraph` as markup. Escape untrusted or literal content:

```python
from xml.sax.saxutils import escape

story.append(Paragraph(escape(owner_supplied_text), styles["BodyCopy"]))
```

## Handle fonts and glyphs deliberately

The built-in PDF fonts cover a limited character set. For accented text, non-Latin scripts,
symbols, or broad Unicode, locate a licensed TrueType/OpenType font on the machine, register
each required face with `pdfmetrics.registerFont(TTFont(...))`, and use those registered names
in every style. Embed the font; do not assume the viewer has it.

Render a page containing representative characters early. Missing glyphs often appear as
black squares or blank space and may not be revealed by text extraction. Avoid substituting
Unicode superscript/subscript characters into a font that lacks them; use ReportLab
`<super>`/`<sub>` markup in `Paragraph` or a registered font that contains the glyph.

## Make complex elements survive pagination

- Use `LongTable(..., repeatRows=1)` for tables that may cross pages.
- Set column widths from the available frame width, not the physical page width.
- Put cell text in `Paragraph` objects so it wraps; never shrink a whole table until it is
  unreadable merely to keep it on one page.
- Use `KeepTogether` for small semantic groups and `KeepWithNext` on heading styles. Do not
  wrap unbounded content in `KeepTogether`.
- Use `PageBreak` only for intentional section boundaries. Let Platypus paginate ordinary
  content.
- Preserve image aspect ratio. Compute the scale from both maximum width and maximum height,
  and use the smaller factor.
- For charts and diagrams, prefer vector ReportLab drawings when practical. Raster images
  should have enough source resolution for their placed size.

## Render, inspect, and revise

Generating without an exception proves only that a PDF file was written. After every
meaningful layout change:

```bash
pdfinfo custom-report.pdf
pdftoppm -png -r 160 custom-report.pdf tmp/rendered/page
```

Inspect every rendered page, not only the first. Check:

- no clipped, overlapping, or missing text;
- no orphan headings, nearly empty spill pages, or accidental blank pages;
- consistent margins, baseline rhythm, heading hierarchy, and whitespace;
- table headers repeat and rows remain readable;
- images are sharp, proportional, and aligned;
- headers, footers, and page numbers do not collide with body content;
- colors remain legible and meaningful in grayscale;
- every required section, figure, and attribution is present.

Revise the source and render again until the latest set of page images has no visible defect.
Never visually approve an older render after changing the PDF.

## Verify the written artifact

Reopen the final file with an available PDF parser such as `pypdf` and check its page count,
metadata, and a few unique text canaries. Text extraction is useful for missing-content checks,
but it is not evidence that layout is correct.

Also verify:

- the file begins with `%PDF-` and has a nontrivial size;
- `pdfinfo` reports the intended page size and page count;
- temporary filenames, debug marks, placeholder copy, and tool tokens are absent;
- document properties do not expose private local paths or unintended personal metadata;
- the final filename and output location are exactly what the owner requested.

Deliver only the final PDF and any source script the owner asked to keep. Remove task-specific
rendered pages and other intermediates when they are no longer needed.
