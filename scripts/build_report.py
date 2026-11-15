"""docs/report/REPORT.md -> docs/report/REPORT.pdf (markdown -> HTML -> fpdf2)."""

from __future__ import annotations

import re
from pathlib import Path

import markdown
from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    md = (ROOT / "docs" / "report" / "REPORT.md").read_text(encoding="utf-8")
    md = re.sub(r"<!-- /?table:\w+ -->", "", md)
    html = markdown.markdown(md, extensions=["tables"])
    html = html.encode("latin-1", "replace").decode("latin-1").replace("<table>", '<table border="1" width="100%">')
    pdf = FPDF(format="A4")
    pdf.set_margins(14, 12, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    pdf.write_html(html, table_line_separators=True)
    out = ROOT / "docs" / "report" / "REPORT.pdf"
    pdf.output(str(out))
    print(out, pdf.page_no(), "pages")


if __name__ == "__main__":
    main()
