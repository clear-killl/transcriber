import os
import re
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .domain import TranscriptSegment, timestamp


def clean_text(text: str) -> str:
    # XML 1.0 forbids these control characters, sometimes present in metadata.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "", text)


def available_output(directory: Path, source: Path, partial: bool = False) -> Path:
    suffix = " — частично" if partial else " — расшифровка"
    # Keep room for the extension and numeric suffix on Windows.
    stem = source.stem[:100].rstrip(" .") or "Запись"
    target = directory / f"{stem}{suffix}.docx"
    number = 2
    while target.exists():
        target = directory / f"{stem}{suffix} ({number}).docx"
        number += 1
    return target


def export_docx(
    target: Path, source: Path, segments: Iterable[TranscriptSegment], *,
    model: str, track_label: str, timestamps: bool, partial: bool = False,
    completed_seconds: float | None = None,
) -> Path:
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2), Cm(2)
    section.left_margin, section.right_margin = Cm(2.5), Cm(2)
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(11)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.15
    language = OxmlElement("w:lang")
    language.set(qn("w:val"), "ru-RU")
    normal.element.get_or_add_rPr().append(language)
    document.core_properties.title = clean_text(source.stem)
    document.core_properties.language = "ru-RU"
    document.core_properties.author = "Транскрибер"
    document.add_heading("Расшифровка записи", 0)
    document.add_paragraph(clean_text(source.name), style="Subtitle")
    metadata = document.add_paragraph()
    metadata.add_run(f"Дата: {datetime.now():%d.%m.%Y %H:%M}\n")
    metadata.add_run(f"Язык: русский  •  Модель: Whisper {model}\n")
    metadata.add_run(clean_text(f"Аудио: {track_label}"))
    if timestamps:
        document.add_paragraph("Таймкоды отсчитываются от начала выбранной аудиодорожки.", style="Caption")
    if partial:
        message = "Частичная расшифровка: обработка прервана."
        if completed_seconds is not None:
            message += f" Сохранено до {timestamp(completed_seconds)}."
        document.add_paragraph(message)
    document.add_paragraph("Текст распознан автоматически. Проверьте имена, числа и неразборчивые места.", style="Caption")
    document.add_heading("Текст записи", 1)
    count = 0
    for segment in segments:
        text = clean_text(segment.text).strip()
        if not text:
            continue
        count += 1
        paragraph = document.add_paragraph()
        if timestamps:
            marker = paragraph.add_run(f"[{timestamp(segment.start)}]  ")
            marker.font.color.rgb = RGBColor.from_string("64748B")
            marker.font.size = Pt(9)
        paragraph.add_run(text)
    if not count:
        document.add_paragraph("Речь не обнаружена в обработанной части записи.")
    footer = section.footer.paragraphs[0]
    footer.alignment = 2
    footer.add_run("Страница ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(suffix=".docx", dir=target.parent)
    os.close(handle)
    try:
        document.save(temporary)
        # An interrupted save cannot leave a truncated Word document.
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target
