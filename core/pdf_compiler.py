import re
import os
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas
from config import ARTIFACTS_DIR

class NumberedCanvas(canvas.Canvas):
    """Adds page numbers and running header/footer."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header rule & title
        self.drawString(54, 755, "Antigravity Assistant • Academic Report")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 747, 558, 747)

        # Footer page number
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 40, page_text)
        self.drawString(54, 40, "Generated via Local AI Assistant")
        self.line(54, 52, 558, 52)
        self.restoreState()

class PDFCompiler:
    @classmethod
    def compile_markdown_to_pdf(cls, title: str, markdown_text: str, filename_prefix: str = "Assignment") -> str:
        """
        Compiles formatted markdown into a professional PDF and returns the absolute file path.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', filename_prefix)
        pdf_filename = f"{safe_prefix}_{timestamp}.pdf"
        output_path = ARTIFACTS_DIR / pdf_filename

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=64,
            bottomMargin=64
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1A202C"),
            spaceAfter=8
        )

        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#4A5568"),
            spaceAfter=15
        )

        h1_style = ParagraphStyle(
            'DocH1',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#2B6CB0"),
            spaceBefore=14,
            spaceAfter=6
        )

        h2_style = ParagraphStyle(
            'DocH2',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#2D3748"),
            spaceBefore=10,
            spaceAfter=4
        )

        body_style = ParagraphStyle(
            'DocBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14.5,
            textColor=colors.HexColor("#2D3748"),
            spaceAfter=6
        )

        bullet_style = ParagraphStyle(
            'DocBullet',
            parent=body_style,
            leftIndent=15,
            spaceAfter=3
        )

        code_style = ParagraphStyle(
            'DocCode',
            parent=styles['Normal'],
            fontName='Courier',
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#1A202C")
        )

        story = []

        # Title Block
        story.append(Paragraph(title, title_style))
        date_str = datetime.now().strftime("%B %d, %Y")
        story.append(Paragraph(f"Date: {date_str} • Author: Imad (via Antigravity)", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=14))

        # Parse Markdown lines
        lines = markdown_text.splitlines()
        in_code_block = False
        code_lines = []

        import html

        def safe_inline(t: str) -> str:
            # Escape XML entities first
            escaped = html.escape(t)
            # Re-apply supported ReportLab formatting
            escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
            escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
            escaped = re.sub(r'`(.*?)`', r'<font face="Courier">\1</font>', escaped)
            return escaped

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code_block:
                    # Closing code block
                    in_code_block = False
                    code_content = "\n".join(code_lines)
                    code_box = Preformatted(code_content, code_style)
                    story.append(Spacer(1, 4))
                    story.append(code_box)
                    story.append(Spacer(1, 6))
                    code_lines = []
                else:
                    # Opening code block
                    in_code_block = True
                    code_lines = []
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            if not stripped:
                story.append(Spacer(1, 4))
                continue

            # Headers
            if stripped.startswith("# "):
                h_text = safe_inline(stripped[2:].strip())
                story.append(Paragraph(h_text, h1_style))
            elif stripped.startswith("## "):
                h_text = safe_inline(stripped[3:].strip())
                story.append(Paragraph(h_text, h2_style))
            elif stripped.startswith("### "):
                h_text = safe_inline(stripped[4:].strip())
                story.append(Paragraph(h_text, h2_style))
            elif stripped.startswith("- ") or stripped.startswith("* "):
                bullet_text = safe_inline(stripped[2:].strip())
                story.append(Paragraph(f"• {bullet_text}", bullet_style))
            elif re.match(r'^\d+\.\s', stripped):
                # Numbered list
                num_text = re.sub(r'^\d+\.\s', '', stripped)
                num_text = safe_inline(num_text)
                story.append(Paragraph(f"&nbsp;&nbsp;{stripped[:3]} {num_text}", bullet_style))
            else:
                # Regular paragraph
                p_text = safe_inline(stripped)
                story.append(Paragraph(p_text, body_style))

        # In case code block wasn't closed
        if in_code_block and code_lines:
            code_content = "\n".join(code_lines)
            story.append(Preformatted(code_content, code_style))

        # Build document
        doc.build(story, canvasmaker=NumberedCanvas)
        print(f"[PDFCompiler] Generated PDF: {output_path}")
        return str(output_path)
