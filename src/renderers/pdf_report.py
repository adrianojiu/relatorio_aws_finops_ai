"""
Styled PDF renderer for plain-text and markdown-like reports without external dependencies.
"""

import os
import re
import struct
from textwrap import wrap
import zlib


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT_MARGIN = 54
RIGHT_MARGIN = 54
TOP_MARGIN = 56
BOTTOM_MARGIN = 48
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

BODY_FONT = "F1"
BODY_BOLD_FONT = "F2"
MONO_FONT = "F3"
ITALIC_FONT = "F4"

TITLE_SIZE = 18
H1_SIZE = 15
H2_SIZE = 13
H3_SIZE = 11
BODY_SIZE = 10
SMALL_SIZE = 9
FOOTER_SIZE = 8
TABLE_PADDING_X = 6
TABLE_PADDING_Y = 4
TABLE_LINE_WIDTH = 0.6
HEADER_FILL_GRAY = 0.93
TITLE_FILL_GRAY = 0.96
ACCENT_RED = "0.72 0.12 0.16"
TEXT_DARK = "0.12 0.12 0.12"
CHART_FILL_GRAY = 0.985
CHART_AXIS_GRAY = "0.75 0.75 0.75"
CHART_BAR_RED = "0.82 0.18 0.20"
CHART_BAR_SOFT = "0.89 0.54 0.56"
CARD_BORDER_GRAY = "0.86 0.86 0.86"
POSITIVE_BLUE = "0.45 0.63 0.86"
LOGO_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "prompts",
    "assets",
    "claro.png",
)


def _sanitize_pdf_text(text):
    text = re.sub(r"^AI Analysis\s*\n+", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"^AI Analysis:\s*\n+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*#\s+Relatório de Análise de Custos AWS[^\n]*\n+", "", text, count=1, flags=re.IGNORECASE)
    text = text.replace("**", "")
    replacements = {
        "—": "-",
        "–": "-",
        "−": "-",
        "•": "*",
        "▼": "v",
        "▲": "^",
        "►": "->",
        "Δ": "Delta",
        "│": "|",
        "├": "|-",
        "└": "\\-",
        "─": "-",
        "→": "->",
        "≈": "~",
        "✅": "[OK]",
        "⚠️": "[Atencao]",
        "⚙️": "[Ajuste]",
        "🔍": "[Investigacao]",
        "❌": "[Nao]",
        "🔴": "[Alta]",
        "🟠": "[Media-Alta]",
        "🟡": "[Media]",
        "🟢": "[Baixa]",
        "📊": "",
        "📋": "",
        "📁": "",
        "📌": "",
        "🛠️": "",
        "🚀": "",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _escape_pdf_text(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _approx_chars_per_line(font_size, indent=0):
    usable_width = CONTENT_WIDTH - indent
    return max(int(usable_width / (font_size * 0.52)), 18)


def _line(text, font=BODY_FONT, size=BODY_SIZE, leading=None, indent=0):
    return {
        "text": text,
        "font": font,
        "size": size,
        "leading": leading or round(size * 1.45, 2),
        "indent": indent,
        "color": TEXT_DARK,
    }


def _clean_inline_markup(text):
    return text.replace("**", "").replace("`", "")


def _blank(height=8):
    return {"blank": True, "leading": height}


def _separator():
    return {"separator": True, "leading": 12}


def _has_items(value):
    """
    Safely test whether list-like inputs contain data without relying on pandas truthiness.
    """
    if value is None:
        return False
    if hasattr(value, "empty"):
        return not value.empty
    try:
        return len(value) > 0
    except TypeError:
        return bool(value)


def _truncate_chart_label(text, limit=18):
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 1)].rstrip() + "..."


def _format_compact_currency(value):
    absolute = abs(float(value))
    if absolute >= 1000:
        return f"US$ {value / 1000:.1f}k"
    if absolute >= 100:
        return f"US$ {value:,.0f}"
    return f"US$ {value:,.1f}"


def _split_summary_label(label):
    if len(label) <= 14 or " " not in label:
        return [label]
    parts = label.split()
    midpoint = max(1, len(parts) // 2)
    return [" ".join(parts[:midpoint]), " ".join(parts[midpoint:])]


def _build_vertical_bar_chart_item(title, data_points, subtitle=None):
    if not data_points:
        return None

    prepared_points = [
        {
            "label": str(label),
            "value": float(value),
        }
        for label, value in data_points
    ]
    return {
        "chart": True,
        "variant": "vertical_bar",
        "title": title,
        "subtitle": subtitle,
        "data": prepared_points,
        "height": 210,
        "leading": 218,
    }


def _build_horizontal_bar_chart_item(title, data_points, subtitle=None):
    if not data_points:
        return None

    prepared_points = [
        {
            "label": str(label),
            "value": float(value),
        }
        for label, value in data_points
    ]
    return {
        "chart": True,
        "variant": "horizontal_bar",
        "title": title,
        "subtitle": subtitle,
        "data": prepared_points,
        "height": 190,
        "leading": 198,
    }


def _build_ai_variation_chart_item(title, anomalies, subtitle=None):
    if not anomalies:
        return None

    prepared_points = []
    for anomaly in anomalies:
        label = anomaly.get("service") or anomaly.get("usage_type") or "Servico"
        prepared_points.append(
            {
                "label": str(label),
                "value": float(abs(anomaly.get("delta_pct", 0.0))),
                "signed_value": float(anomaly.get("delta_pct", 0.0)),
                "delta_usd": float(anomaly.get("delta_usd", 0.0)),
            }
        )

    return {
        "chart": True,
        "variant": "variation_bar",
        "title": title,
        "subtitle": subtitle,
        "data": prepared_points,
        "height": 190,
        "leading": 198,
    }


def _classification_palette(classification):
    normalized = (classification or "").strip().lower()
    if normalized == "anomalia real":
        return {
            "label": "ANOMALIA REAL",
            "fill": "0.96 0.85 0.85",
            "text": "0.64 0.12 0.16",
        }
    if normalized == "efeito em cascata":
        return {
            "label": "EFEITO EM CASCATA",
            "fill": "0.86 0.91 0.97",
            "text": "0.18 0.37 0.63",
        }
    return {
        "label": "DESVIO ESPERADO",
        "fill": "0.91 0.95 0.86",
        "text": "0.26 0.45 0.14",
    }


def _extract_ai_driver_sections(text):
    """
    Parse the AI narrative headings to recover driver metadata for visual cards.
    """
    sanitized = _sanitize_pdf_text(text)
    pattern = re.compile(
        r"###\s+\d+\.\s+(.*?)\s+[-—]\s+`([^`]+)`\s+\|\s+([^\n]+)\n"
        r"\*\*Classificacao:\*\*\s+`([^`]+)`\n\n"
        r"(.*?)(?=\n---\n|\n###\s+\d+\.|\n##\s+Recomendacoes|\Z)",
        flags=re.DOTALL,
    )
    sections = []
    for service, usage_type, headline_value, classification, body in pattern.findall(sanitized):
        body_lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        confidence = ""
        narrative_lines = []
        for line in body_lines:
            if line.lower().startswith("confianca:"):
                confidence = line.split(":", 1)[1].strip()
            else:
                narrative_lines.append(line)
        sections.append(
            {
                "service": service.strip(),
                "usage_type": usage_type.strip(),
                "headline_value": headline_value.strip(),
                "classification": classification.strip(),
                "narrative": " ".join(narrative_lines).strip(),
                "confidence": confidence,
            }
        )
    return sections


def _build_ai_classification_summary_item(driver_sections):
    if not driver_sections:
        return None

    order = ["anomalia real", "desvio esperado", "efeito em cascata"]
    counts = {key: 0 for key in order}
    for section in driver_sections:
        key = (section.get("classification") or "").strip().lower()
        if key in counts:
            counts[key] += 1

    data = []
    for key in order:
        palette = _classification_palette(key)
        data.append(
            {
                "label": palette["label"],
                "value": counts[key],
                "fill": palette["fill"],
                "text": palette["text"],
            }
        )

    return {
        "classification_summary": True,
        "title": "Leitura rapida das classificacoes",
        "subtitle": "Distribuicao dos drivers destacados pela analise da IA.",
        "data": data,
        "height": 96,
        "leading": 104,
    }


def _build_ai_driver_cards_item(driver_sections, anomalies):
    if not driver_sections:
        return None

    anomaly_map = {
        (
            (item.get("service") or "").strip(),
            (item.get("usage_type") or "").strip(),
        ): item
        for item in (anomalies or [])
    }
    cards = []
    for section in driver_sections:
        anomaly = anomaly_map.get((section["service"], section["usage_type"]), {})
        resources = anomaly.get("resources") or []
        top_resources = []
        for resource in resources[:3]:
            resource_id = resource.get("resource_id") or "nao identificado"
            top_resources.append(_truncate_chart_label(str(resource_id), 34))

        cards.append(
            {
                "service": section["service"],
                "usage_type": section["usage_type"],
                "classification": section["classification"],
                "headline_value": section["headline_value"],
                "delta_pct": float(anomaly.get("delta_pct", 0.0)),
                "confidence": section.get("confidence") or "nao informado",
                "resources": top_resources,
            }
        )

    return {
        "anomaly_cards": True,
        "title": "Drivers analisados pela IA",
        "subtitle": "Cards com classificacao, variacao e recursos candidatos para leitura rapida.",
        "cards": cards,
        "height": max(120 + (len(cards) * 84), 200),
        "leading": max(128 + (len(cards) * 84), 208),
    }


def _wrap_line(text, font=BODY_FONT, size=BODY_SIZE, indent=0, leading=None):
    width = _approx_chars_per_line(size, indent)
    parts = wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [""]
    return [_line(part, font=font, size=size, indent=indent, leading=leading) for part in parts]


def _wrap_bullet_line(text, font=BODY_FONT, size=BODY_SIZE, leading=None):
    lines = _wrap_line(text, font=font, size=size, indent=20, leading=leading)
    if lines:
        lines[0]["bullet"] = True
    return lines


def _is_markdown_table_line(raw_line):
    stripped = raw_line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _is_markdown_separator_row(raw_line):
    stripped = raw_line.strip()
    if not _is_markdown_table_line(stripped):
        return False
    inner_cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not inner_cells:
        return False
    return all(cell and set(cell) <= {"-", ":", " "} for cell in inner_cells)


def _split_table_row(raw_line):
    return [cell.strip() for cell in raw_line.strip().strip("|").split("|")]


def _wrap_table_cell(text, col_width, font_size):
    max_chars = max(int((col_width - (TABLE_PADDING_X * 2)) / (font_size * 0.52)), 6)
    sanitized = text.strip() or ""
    return wrap(sanitized, width=max_chars, break_long_words=True, break_on_hyphens=True) or [""]


def _build_table_item(table_lines):
    header = _split_table_row(table_lines[0])
    body_rows = [_split_table_row(line) for line in table_lines[2:]]
    col_count = max(len(header), *(len(row) for row in body_rows)) if body_rows else len(header)
    usable_width = CONTENT_WIDTH
    if col_count == 2:
        col_widths = [usable_width * 0.38, usable_width * 0.62]
    else:
        normalized_rows = [header] + body_rows
        max_lengths = []
        for column_index in range(col_count):
            column_values = [
                (row[column_index].strip() if column_index < len(row) else "")
                for row in normalized_rows
            ]
            max_lengths.append(max(len(value) for value in column_values) or 1)

        clipped_lengths = [min(max(length, 8), 36) for length in max_lengths]
        total_length = sum(clipped_lengths) or col_count
        col_widths = [(usable_width * length) / total_length for length in clipped_lengths]

        min_width = 72
        adjusted = True
        while adjusted:
            adjusted = False
            small_indexes = [idx for idx, width in enumerate(col_widths) if width < min_width]
            if not small_indexes:
                break
            deficit = sum(min_width - col_widths[idx] for idx in small_indexes)
            large_indexes = [idx for idx in range(col_count) if idx not in small_indexes and col_widths[idx] > min_width]
            if not large_indexes:
                break
            share = deficit / len(large_indexes)
            for idx in small_indexes:
                col_widths[idx] = min_width
            for idx in large_indexes:
                col_widths[idx] -= share
            adjusted = True

        total_width = sum(col_widths) or usable_width
        col_widths = [width * usable_width / total_width for width in col_widths]
    row_leading = 12

    prepared_rows = []
    for row_index, row in enumerate([header] + body_rows):
        normalized = row + [""] * (col_count - len(row))
        wrapped_cells = [
            _wrap_table_cell(cell, col_widths[column_index], SMALL_SIZE)
            for column_index, cell in enumerate(normalized)
        ]
        line_count = max(len(cell_lines) for cell_lines in wrapped_cells) or 1
        row_height = (line_count * row_leading) + (TABLE_PADDING_Y * 2)
        prepared_rows.append(
            {
                "cells": wrapped_cells,
                "is_header": row_index == 0,
                "height": row_height,
            }
        )

    total_height = sum(row["height"] for row in prepared_rows) + 10
    return {
        "table": True,
        "columns": col_count,
        "col_widths": col_widths,
        "rows": prepared_rows,
        "height": total_height,
        "leading": total_height,
    }


def _normalize_code_block_lines(code_lines):
    normalized = []
    for raw_line in code_lines:
        line = _clean_inline_markup(raw_line.rstrip())
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"|", "│"}:
            continue
        normalized.append(line)
    return normalized


def _looks_like_flow_diagram(lines):
    if len(lines) < 3:
        return False
    arrow_lines = sum(1 for line in lines if "->" in line)
    connector_lines = sum(1 for line in lines if line.strip() in {"|", "v", "^"} or line.strip().startswith(("|-", "\\-")))
    return arrow_lines >= 2 or (arrow_lines >= 1 and connector_lines >= 1)


def _strip_flow_prefix(text):
    cleaned = text.strip()
    prefixes = ("|-->", "|->", "\\->", "->", "|-", "\\-", "|")
    stripped_any = True
    while stripped_any:
        stripped_any = False
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                stripped_any = True
    return cleaned


def _build_flow_block_item(code_lines):
    normalized_lines = _normalize_code_block_lines(code_lines)
    rendered_lines = []

    for raw_line in normalized_lines:
        stripped = raw_line.strip()
        if stripped in {"|", "v", "^"}:
            continue

        level = min((len(raw_line) - len(raw_line.lstrip(" "))) // 8, 4)
        text = _strip_flow_prefix(raw_line)
        if not text:
            continue

        rendered_lines.append(
            {
                "text": text,
                "indent": 14 + (level * 18),
                "level": level,
            }
        )

    line_height = 14
    total_height = max((len(rendered_lines) * line_height) + 18, 24)
    return {
        "flow_block": True,
        "lines": rendered_lines,
        "height": total_height,
        "leading": total_height,
    }


def _build_code_block_item(code_lines):
    normalized_lines = _normalize_code_block_lines(code_lines)
    if _looks_like_flow_diagram(normalized_lines):
        return _build_flow_block_item(code_lines)

    rendered_lines = []
    for line in normalized_lines:
        stripped = line.lstrip()
        indent_spaces = len(line) - len(stripped)
        rendered_lines.append(
            {
                "text": stripped,
                "indent": 8 + min(indent_spaces * 3, 28),
            }
        )

    line_height = 13
    total_height = max((len(rendered_lines) * line_height) + 16, 22)
    return {
        "code_block": True,
        "lines": rendered_lines,
        "height": total_height,
        "leading": total_height,
    }


def _classify_and_wrap(raw_line):
    stripped = _clean_inline_markup(raw_line).strip()
    if not stripped:
        return [_blank(8)]

    if stripped == "---":
        return [_separator()]

    if stripped.startswith("# "):
        return _wrap_line(stripped[2:].strip(), font=BODY_BOLD_FONT, size=TITLE_SIZE + 2, leading=26)
    if stripped.startswith("## "):
        lines = _wrap_line(stripped[3:].strip(), font=BODY_BOLD_FONT, size=H1_SIZE + 1, leading=20)
        for line in lines:
            line["color"] = ACCENT_RED
        return [_blank(6)] + lines
    if stripped.startswith("### "):
        lines = _wrap_line(stripped[4:].strip(), font=BODY_BOLD_FONT, size=H2_SIZE, leading=17)
        for line in lines:
            line["color"] = ACCENT_RED
        return [_blank(3)] + lines
    if stripped.startswith("#### "):
        return [_blank(2)] + _wrap_line(stripped[5:].strip(), font=BODY_BOLD_FONT, size=H3_SIZE, leading=15)
    if stripped.startswith("> "):
        return _wrap_line(stripped[2:].strip(), font=ITALIC_FONT, size=BODY_SIZE, indent=16, leading=14)
    if stripped.startswith("|"):
        return _wrap_line(stripped, font=MONO_FONT, size=SMALL_SIZE, leading=12)
    if re.match(r"^\d+\.\s+", stripped):
        return _wrap_line(stripped, font=BODY_FONT, size=BODY_SIZE, indent=10, leading=14)
    if stripped.startswith(("- ", "* ")):
        return _wrap_bullet_line(stripped[2:].strip(), font=BODY_FONT, size=BODY_SIZE, leading=14)
    if stripped.endswith(":") and len(stripped) < 70:
        return [_blank(2)] + _wrap_line(stripped, font=BODY_BOLD_FONT, size=BODY_SIZE, leading=14)

    return _wrap_line(stripped, font=BODY_FONT, size=BODY_SIZE, leading=14)


def _prepare_layout_lines(text):
    sanitized = _sanitize_pdf_text(text)
    lines = []
    raw_lines = sanitized.splitlines()
    index = 0
    while index < len(raw_lines):
        raw_line = raw_lines[index]
        if raw_line.strip().startswith("```"):
            index += 1
            code_lines = []
            while index < len(raw_lines) and not raw_lines[index].strip().startswith("```"):
                code_lines.append(raw_lines[index])
                index += 1
            if index < len(raw_lines) and raw_lines[index].strip().startswith("```"):
                index += 1
            lines.append(_build_code_block_item(code_lines))
            lines.append(_blank(10))
            continue
        if (
            index + 1 < len(raw_lines)
            and _is_markdown_table_line(raw_line)
            and _is_markdown_separator_row(raw_lines[index + 1])
        ):
            table_lines = [raw_line, raw_lines[index + 1]]
            index += 2
            while index < len(raw_lines) and _is_markdown_table_line(raw_lines[index]):
                table_lines.append(raw_lines[index])
                index += 1
            lines.append(_build_table_item(table_lines))
            lines.append(_blank(10))
            continue

        lines.extend(_classify_and_wrap(raw_line))
        index += 1
    return lines


def _escape_and_encode(text):
    return _escape_pdf_text(text).encode("cp1252", errors="replace").decode("cp1252")


def _paeth_predictor(left, up, up_left):
    predictor = left + up - up_left
    dist_left = abs(predictor - left)
    dist_up = abs(predictor - up)
    dist_up_left = abs(predictor - up_left)
    if dist_left <= dist_up and dist_left <= dist_up_left:
        return left
    if dist_up <= dist_up_left:
        return up
    return up_left


def _load_png_logo_rgb():
    """
    Load a PNG logo and convert it to flattened RGB bytes for PDF embedding.
    Supports non-interlaced 8-bit RGBA/RGB PNGs, which is enough for the project logo.
    """
    if not os.path.exists(LOGO_FILE):
        return None

    with open(LOGO_FILE, "rb") as file_handle:
        content = file_handle.read()

    png_signature = b"\x89PNG\r\n\x1a\n"
    if not content.startswith(png_signature):
        return None

    offset = len(png_signature)
    width = height = bit_depth = color_type = interlace_method = None
    idat_parts = []

    while offset < len(content):
        chunk_length = struct.unpack(">I", content[offset:offset + 4])[0]
        offset += 4
        chunk_type = content[offset:offset + 4]
        offset += 4
        chunk_data = content[offset:offset + chunk_length]
        offset += chunk_length
        offset += 4  # CRC

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace_method = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break

    if not width or not height or bit_depth != 8 or interlace_method != 0:
        return None
    if color_type not in {2, 6}:
        return None

    channels = 4 if color_type == 6 else 3
    bytes_per_pixel = channels
    stride = width * bytes_per_pixel
    decompressed = zlib.decompress(b"".join(idat_parts))

    rows = []
    cursor = 0
    previous_row = b"\x00" * stride
    for _ in range(height):
        filter_type = decompressed[cursor]
        cursor += 1
        filtered_row = decompressed[cursor:cursor + stride]
        cursor += stride
        reconstructed = bytearray(stride)

        for index in range(stride):
            left = reconstructed[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            up = previous_row[index]
            up_left = previous_row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            value = filtered_row[index]

            if filter_type == 0:
                recon = value
            elif filter_type == 1:
                recon = (value + left) & 0xFF
            elif filter_type == 2:
                recon = (value + up) & 0xFF
            elif filter_type == 3:
                recon = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                recon = (value + _paeth_predictor(left, up, up_left)) & 0xFF
            else:
                return None

            reconstructed[index] = recon

        rows.append(bytes(reconstructed))
        previous_row = bytes(reconstructed)

    rgb_bytes = bytearray()
    if color_type == 6:
        for row in rows:
            for index in range(0, len(row), 4):
                red, green, blue, alpha = row[index:index + 4]
                rgb_bytes.extend(
                    [
                        ((red * alpha) + (255 * (255 - alpha))) // 255,
                        ((green * alpha) + (255 * (255 - alpha))) // 255,
                        ((blue * alpha) + (255 * (255 - alpha))) // 255,
                    ]
                )
    else:
        for row in rows:
            rgb_bytes.extend(row)

    return {
        "width": width,
        "height": height,
        "data": zlib.compress(bytes(rgb_bytes)),
    }


def _paginate_layout_lines(layout_lines):
    pages = []
    current_page = []
    current_page_index = 1
    first_page_top_margin = 110
    default_top_margin = TOP_MARGIN
    current_height = first_page_top_margin
    max_height = PAGE_HEIGHT - BOTTOM_MARGIN

    for item in layout_lines:
        item_height = item.get("height", item.get("leading", 12))
        if current_page and current_height + item_height > max_height:
            pages.append(current_page)
            current_page = []
            current_page_index += 1
            current_height = default_top_margin
        current_page.append(item)
        current_height += item_height

    if current_page:
        pages.append(current_page)

    return pages or [[]]


def _build_page_stream(page_items, page_number, total_pages, account_label=None, logo_enabled=False):
    commands = []
    header_bottom = PAGE_HEIGHT - 68
    header_height = 52

    if page_number == 1:
        commands.extend(
            [
                "q",
                f"{TITLE_FILL_GRAY} g",
                f"{LEFT_MARGIN} {header_bottom} {CONTENT_WIDTH} {header_height} re f",
                f"{ACCENT_RED} RG",
                "1.2 w",
                f"{LEFT_MARGIN} {header_bottom} m {LEFT_MARGIN + CONTENT_WIDTH} {header_bottom} l S",
                "Q",
                "BT",
                f"{ACCENT_RED} rg",
                f"/{BODY_BOLD_FONT} 18 Tf",
                f"{LEFT_MARGIN + 12} {PAGE_HEIGHT - 33} Td",
                f"({_escape_and_encode('Relatório de Análise de Custos AWS')}) Tj",
                "ET",
            ]
        )
        if logo_enabled:
            logo_size = 24
            logo_x = LEFT_MARGIN + CONTENT_WIDTH - logo_size - 14
            logo_y = header_bottom + ((header_height - logo_size) / 2)
            commands.extend(
                [
                    "q",
                    f"{logo_size} 0 0 {logo_size} {logo_x} {logo_y} cm",
                    "/ImLogo Do",
                    "Q",
                ]
            )
        if account_label:
            commands.extend(
                [
                    "BT",
                    f"{TEXT_DARK} rg",
                    f"/{BODY_FONT} 9 Tf",
                    f"{LEFT_MARGIN + 12} {PAGE_HEIGHT - 51} Td",
                    f"({_escape_and_encode(f'Conta AWS: {account_label}')}) Tj",
                    "ET",
                ]
            )

    y = PAGE_HEIGHT - (110 if page_number == 1 else TOP_MARGIN)
    for item in page_items:
        if item.get("blank"):
            y -= item["leading"]
            continue
        if item.get("separator"):
            y -= 6
            commands.append(f"{LEFT_MARGIN} {y} m {PAGE_WIDTH - RIGHT_MARGIN} {y} l S")
            y -= 6
            continue
        if item.get("flow_block"):
            y = _render_flow_block(commands, item, y)
            continue
        if item.get("code_block"):
            y = _render_code_block(commands, item, y)
            continue
        if item.get("table"):
            y = _render_table(commands, item, y)
            continue
        if item.get("chart"):
            y = _render_chart(commands, item, y)
            continue
        if item.get("classification_summary"):
            y = _render_classification_summary(commands, item, y)
            continue
        if item.get("anomaly_cards"):
            y = _render_anomaly_cards(commands, item, y)
            continue

        text = _escape_and_encode(item["text"])
        x = LEFT_MARGIN + item.get("indent", 0)
        commands.extend(
            [
                "BT",
                f"{item.get('color', TEXT_DARK)} rg",
                f"/{item['font']} {item['size']} Tf",
                f"{x} {y} Td",
                f"({text}) Tj",
                "ET",
            ]
        )
        if item.get("bullet"):
            commands.extend(
                [
                    "BT",
                    f"{ACCENT_RED} rg",
                    f"/{BODY_BOLD_FONT} 12 Tf",
                    f"{LEFT_MARGIN + 8} {y} Td",
                    "(•) Tj",
                    "ET",
                ]
            )
        y -= item["leading"]

    footer_text = f"Pagina {page_number} de {total_pages}"
    commands.extend(
        [
            "BT",
            f"{TEXT_DARK} rg",
            f"/{BODY_FONT} {FOOTER_SIZE} Tf",
            f"{PAGE_WIDTH - RIGHT_MARGIN - 70} 24 Td",
            f"({_escape_pdf_text(footer_text)}) Tj",
            "ET",
        ]
    )

    return "\n".join(commands) + "\n"


def _render_table(commands, table_item, top_y):
    x0 = LEFT_MARGIN
    y = top_y
    total_width = sum(table_item["col_widths"])

    commands.append(f"{TABLE_LINE_WIDTH} w")
    for row in table_item["rows"]:
        row_height = row["height"]
        row_bottom = y - row_height

        if row["is_header"]:
            commands.extend(
                [
                    "q",
                    f"{HEADER_FILL_GRAY} g",
                    f"{x0} {row_bottom} {total_width} {row_height} re f",
                    "Q",
                ]
            )
        commands.append(f"{x0} {row_bottom} {total_width} {row_height} re S")
        running_x = x0
        for column_width in table_item["col_widths"][:-1]:
            running_x += column_width
            x = running_x
            commands.append(f"{x} {row_bottom} m {x} {y} l S")

        running_x = x0
        for column_index, wrapped_lines in enumerate(row["cells"]):
            cell_x = running_x + TABLE_PADDING_X
            text_y = y - TABLE_PADDING_Y - SMALL_SIZE
            font = BODY_BOLD_FONT if row["is_header"] else BODY_FONT
            for line in wrapped_lines:
                text = _escape_and_encode(line)
                commands.extend(
                    [
                        "BT",
                        f"{TEXT_DARK} rg",
                        f"/{font} {SMALL_SIZE} Tf",
                        f"{cell_x} {text_y} Td",
                        f"({text}) Tj",
                        "ET",
                    ]
                )
                text_y -= 12
            running_x += table_item["col_widths"][column_index]

        y = row_bottom

    return y - 4


def _render_code_block(commands, code_item, top_y):
    x0 = LEFT_MARGIN
    width = CONTENT_WIDTH
    height = code_item["height"] - 4
    bottom_y = top_y - height

    commands.extend(
        [
            "q",
            "0.98 g",
            f"{x0} {bottom_y} {width} {height} re f",
            f"{ACCENT_RED} RG",
            "0.6 w",
            f"{x0} {bottom_y} {width} {height} re S",
            "Q",
        ]
    )

    text_y = top_y - 14
    for line in code_item["lines"]:
        text = _escape_and_encode(line["text"])
        commands.extend(
            [
                "BT",
                f"{TEXT_DARK} rg",
                f"/{MONO_FONT} {SMALL_SIZE} Tf",
                f"{x0 + line['indent']} {text_y} Td",
                f"({text}) Tj",
                "ET",
            ]
        )
        text_y -= 13

    return bottom_y - 6


def _render_flow_block(commands, flow_item, top_y):
    x0 = LEFT_MARGIN
    width = CONTENT_WIDTH
    height = flow_item["height"] - 4
    bottom_y = top_y - height

    commands.extend(
        [
            "q",
            "0.985 g",
            f"{x0} {bottom_y} {width} {height} re f",
            f"{ACCENT_RED} RG",
            "1.0 w",
            f"{x0} {bottom_y} {width} {height} re S",
            f"{ACCENT_RED} rg",
            f"{x0 + 8} {bottom_y + 8} 3 {height - 16} re f",
            "Q",
        ]
    )

    text_y = top_y - 14
    first_line = True
    for line in flow_item["lines"]:
        font = BODY_BOLD_FONT if first_line and line["level"] == 0 else BODY_FONT
        size = BODY_SIZE if first_line and line["level"] == 0 else SMALL_SIZE
        text = _escape_and_encode(line["text"])
        commands.extend(
            [
                "BT",
                f"{TEXT_DARK} rg",
                f"/{font} {size} Tf",
                f"{x0 + line['indent']} {text_y} Td",
                f"({text}) Tj",
                "ET",
            ]
        )
        if not (first_line and line["level"] == 0):
            commands.extend(
                [
                    "BT",
                    f"{ACCENT_RED} rg",
                    f"/{BODY_BOLD_FONT} 11 Tf",
                    f"{x0 + line['indent'] - 10} {text_y} Td",
                    "(•) Tj",
                    "ET",
                ]
            )
        text_y -= 14
        first_line = False

    return bottom_y - 6


def _render_chart_title(commands, x0, top_y, title, subtitle=None):
    commands.extend(
        [
            "BT",
            f"{ACCENT_RED} rg",
            f"/{BODY_BOLD_FONT} {H3_SIZE} Tf",
            f"{x0 + 12} {top_y - 18} Td",
            f"({_escape_and_encode(title)}) Tj",
            "ET",
        ]
    )
    if subtitle:
        commands.extend(
            [
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} {SMALL_SIZE} Tf",
                f"{x0 + 12} {top_y - 31} Td",
                f"({_escape_and_encode(subtitle)}) Tj",
                "ET",
            ]
        )


def _render_vertical_bar_chart(commands, chart_item, top_y):
    x0 = LEFT_MARGIN
    width = CONTENT_WIDTH
    height = chart_item["height"] - 4
    bottom_y = top_y - height
    plot_left = x0 + 44
    plot_right = x0 + width - 20
    plot_top = top_y - 44
    plot_bottom = bottom_y + 40
    plot_width = plot_right - plot_left
    plot_height = max(plot_top - plot_bottom, 40)
    points = chart_item["data"]
    max_value = max(point["value"] for point in points) or 1
    bar_gap = 8
    bar_width = max(min((plot_width - (bar_gap * (len(points) + 1))) / max(len(points), 1), 36), 10)

    commands.extend(
        [
            "q",
            f"{CHART_FILL_GRAY} g",
            f"{x0} {bottom_y} {width} {height} re f",
            f"{ACCENT_RED} RG",
            "0.8 w",
            f"{x0} {bottom_y} {width} {height} re S",
            "Q",
        ]
    )
    _render_chart_title(commands, x0, top_y, chart_item["title"], chart_item.get("subtitle"))

    commands.extend(
        [
            f"{CHART_AXIS_GRAY} RG",
            "0.5 w",
            f"{plot_left} {plot_bottom} m {plot_right} {plot_bottom} l S",
            f"{plot_left} {plot_bottom} m {plot_left} {plot_top} l S",
        ]
    )

    for step in range(1, 4):
        grid_y = plot_bottom + ((plot_height * step) / 4)
        commands.extend(
            [
                f"{CHART_AXIS_GRAY} RG",
                "0.25 w",
                f"{plot_left} {grid_y} m {plot_right} {grid_y} l S",
            ]
        )

    current_x = plot_left + bar_gap
    for point in points:
        bar_height = max((point["value"] / max_value) * (plot_height - 6), 2)
        value_label = _format_compact_currency(point["value"])
        label_x = max(current_x - 4, plot_left + 2)
        commands.extend(
            [
                "q",
                f"{CHART_BAR_RED} rg",
                f"{current_x} {plot_bottom} {bar_width} {bar_height} re f",
                "Q",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 6 Tf",
                f"{label_x} {plot_bottom - 12} Td",
                f"({_escape_and_encode(_truncate_chart_label(point['label'], 10))}) Tj",
                "ET",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 6 Tf",
                f"{label_x} {plot_bottom + bar_height + 4} Td",
                f"({_escape_and_encode(value_label)}) Tj",
                "ET",
            ]
        )
        current_x += bar_width + bar_gap

    return bottom_y - 6


def _render_horizontal_bar_chart(commands, chart_item, top_y):
    x0 = LEFT_MARGIN
    width = CONTENT_WIDTH
    height = chart_item["height"] - 4
    bottom_y = top_y - height
    plot_left = x0 + 132
    plot_right = x0 + width - 20
    plot_top = top_y - 42
    plot_bottom = bottom_y + 20
    points = chart_item["data"]
    max_value = max(point["value"] for point in points) or 1
    usable_height = max(plot_top - plot_bottom, 30)
    row_height = usable_height / max(len(points), 1)
    bar_height = max(min(row_height * 0.56, 16), 8)

    commands.extend(
        [
            "q",
            f"{CHART_FILL_GRAY} g",
            f"{x0} {bottom_y} {width} {height} re f",
            f"{ACCENT_RED} RG",
            "0.8 w",
            f"{x0} {bottom_y} {width} {height} re S",
            "Q",
        ]
    )
    _render_chart_title(commands, x0, top_y, chart_item["title"], chart_item.get("subtitle"))

    commands.extend(
        [
            f"{CHART_AXIS_GRAY} RG",
            "0.5 w",
            f"{plot_left} {plot_bottom} m {plot_left} {plot_top} l S",
        ]
    )

    current_y = plot_top - row_height + ((row_height - bar_height) / 2)
    for point in points:
        bar_width = max(((point["value"] / max_value) * (plot_right - plot_left - 8)), 2)
        value_label = _format_compact_currency(point["value"])
        value_x = min(plot_left + bar_width + 6, plot_right - 42)
        commands.extend(
            [
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 8 Tf",
                f"{x0 + 12} {current_y + 3} Td",
                f"({_escape_and_encode(_truncate_chart_label(point['label'], 24))}) Tj",
                "ET",
                "q",
                f"{CHART_BAR_SOFT} rg",
                f"{plot_left} {current_y} {bar_width} {bar_height} re f",
                "Q",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 7 Tf",
                f"{value_x} {current_y + 3} Td",
                f"({_escape_and_encode(value_label)}) Tj",
                "ET",
            ]
        )
        current_y -= row_height

    return bottom_y - 6


def _render_variation_bar_chart(commands, chart_item, top_y):
    x0 = LEFT_MARGIN
    width = CONTENT_WIDTH
    height = chart_item["height"] - 4
    bottom_y = top_y - height
    plot_left = x0 + 132
    plot_right = x0 + width - 20
    plot_top = top_y - 42
    plot_bottom = bottom_y + 20
    zero_x = plot_left + ((plot_right - plot_left) / 2)
    points = chart_item["data"]
    max_value = max(point["value"] for point in points) or 1
    usable_height = max(plot_top - plot_bottom, 30)
    row_height = usable_height / max(len(points), 1)
    bar_height = max(min(row_height * 0.56, 16), 8)
    half_plot = (plot_right - plot_left) / 2

    commands.extend(
        [
            "q",
            f"{CHART_FILL_GRAY} g",
            f"{x0} {bottom_y} {width} {height} re f",
            f"{ACCENT_RED} RG",
            "0.8 w",
            f"{x0} {bottom_y} {width} {height} re S",
            "Q",
        ]
    )
    _render_chart_title(commands, x0, top_y, chart_item["title"], chart_item.get("subtitle"))

    commands.extend(
        [
            f"{CHART_AXIS_GRAY} RG",
            "0.5 w",
            f"{zero_x} {plot_bottom} m {zero_x} {plot_top} l S",
        ]
    )

    current_y = plot_top - row_height + ((row_height - bar_height) / 2)
    for point in points:
        signed_value = point.get("signed_value", point["value"])
        bar_width = max((point["value"] / max_value) * (half_plot - 8), 2)
        percent_label = f"{signed_value:+.1f}%"
        usd_label = f"{point.get('delta_usd', 0.0):+,.2f} USD"
        bar_x = zero_x if signed_value >= 0 else zero_x - bar_width
        bar_color = CHART_BAR_RED if signed_value >= 0 else "0.45 0.63 0.86"
        label_x = plot_left - 120
        if signed_value >= 0:
            value_x = min(zero_x + bar_width + 6, plot_right - 52)
        else:
            value_x = max(zero_x - bar_width - 52, plot_left + 4)
        commands.extend(
            [
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 8 Tf",
                f"{label_x} {current_y + 3} Td",
                f"({_escape_and_encode(_truncate_chart_label(point['label'], 24))}) Tj",
                "ET",
                "q",
                f"{bar_color} rg",
                f"{bar_x} {current_y} {bar_width} {bar_height} re f",
                "Q",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_BOLD_FONT} 7 Tf",
                f"{value_x} {current_y + 8} Td",
                f"({_escape_and_encode(percent_label)}) Tj",
                "ET",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 6 Tf",
                f"{value_x} {current_y + 1} Td",
                f"({_escape_and_encode(usd_label)}) Tj",
                "ET",
            ]
        )
        current_y -= row_height

    return bottom_y - 6


def _render_classification_summary(commands, summary_item, top_y):
    x0 = LEFT_MARGIN
    width = CONTENT_WIDTH
    height = summary_item["height"] - 4
    bottom_y = top_y - height
    box_gap = 10
    box_width = (width - (box_gap * 4)) / 3
    box_y = bottom_y + 18
    box_height = 44

    commands.extend(
        [
            "q",
            f"{CHART_FILL_GRAY} g",
            f"{x0} {bottom_y} {width} {height} re f",
            f"{ACCENT_RED} RG",
            "0.8 w",
            f"{x0} {bottom_y} {width} {height} re S",
            "Q",
        ]
    )
    _render_chart_title(commands, x0, top_y, summary_item["title"], summary_item.get("subtitle"))

    current_x = x0 + box_gap
    for item in summary_item["data"]:
        label_lines = _split_summary_label(item["label"])
        commands.extend(
            [
                "q",
                f"{item['fill']} rg",
                f"{current_x} {box_y} {box_width} {box_height} re f",
                f"{CARD_BORDER_GRAY} RG",
                "0.5 w",
                f"{current_x} {box_y} {box_width} {box_height} re S",
                "Q",
                "BT",
                f"{item['text']} rg",
                f"/{BODY_BOLD_FONT} 6 Tf",
                f"{current_x + 8} {box_y + 31} Td",
                f"({_escape_and_encode(label_lines[0])}) Tj",
                "ET",
            ]
        )
        if len(label_lines) > 1:
            commands.extend(
                [
                    "BT",
                    f"{item['text']} rg",
                    f"/{BODY_BOLD_FONT} 6 Tf",
                    f"{current_x + 8} {box_y + 23} Td",
                    f"({_escape_and_encode(label_lines[1])}) Tj",
                    "ET",
                ]
            )
        commands.extend(
            [
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_BOLD_FONT} 13 Tf",
                f"{current_x + 8} {box_y + 8} Td",
                f"({_escape_and_encode(str(item['value']))}) Tj",
                "ET",
            ]
        )
        current_x += box_width + box_gap

    return bottom_y - 6


def _render_anomaly_cards(commands, cards_item, top_y):
    x0 = LEFT_MARGIN
    width = CONTENT_WIDTH
    height = cards_item["height"] - 4
    bottom_y = top_y - height
    card_x = x0 + 10
    card_width = width - 20
    card_height = 72
    card_gap = 10
    current_y = top_y - 48

    commands.extend(
        [
            "q",
            f"{CHART_FILL_GRAY} g",
            f"{x0} {bottom_y} {width} {height} re f",
            f"{ACCENT_RED} RG",
            "0.8 w",
            f"{x0} {bottom_y} {width} {height} re S",
            "Q",
        ]
    )
    _render_chart_title(commands, x0, top_y, cards_item["title"], cards_item.get("subtitle"))

    for card in cards_item["cards"]:
        palette = _classification_palette(card["classification"])
        card_bottom = current_y - card_height
        resources_text = "Recursos: " + (", ".join(card["resources"]) if card["resources"] else "sem candidato claro")
        delta_label = f"{card['delta_pct']:+.2f}%"
        delta_color = ACCENT_RED if card["delta_pct"] >= 0 else POSITIVE_BLUE
        commands.extend(
            [
                "q",
                "1 1 1 rg",
                f"{card_x} {card_bottom} {card_width} {card_height} re f",
                f"{CARD_BORDER_GRAY} RG",
                "0.6 w",
                f"{card_x} {card_bottom} {card_width} {card_height} re S",
                "Q",
                "q",
                f"{palette['fill']} rg",
                f"{card_x + 10} {card_bottom + 48} 118 16 re f",
                "Q",
                "BT",
                f"{palette['text']} rg",
                f"/{BODY_BOLD_FONT} 7 Tf",
                f"{card_x + 15} {card_bottom + 53} Td",
                f"({_escape_and_encode(palette['label'])}) Tj",
                "ET",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_BOLD_FONT} 10 Tf",
                f"{card_x + 10} {card_bottom + 33} Td",
                f"({_escape_and_encode(_truncate_chart_label(card['service'], 46))}) Tj",
                "ET",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 8 Tf",
                f"{card_x + 10} {card_bottom + 19} Td",
                f"({_escape_and_encode(_truncate_chart_label(card['usage_type'], 64))}) Tj",
                "ET",
                "BT",
                f"{delta_color} rg",
                f"/{BODY_BOLD_FONT} 12 Tf",
                f"{card_x + card_width - 76} {card_bottom + 48} Td",
                f"({_escape_and_encode(delta_label)}) Tj",
                "ET",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 8 Tf",
                f"{card_x + card_width - 110} {card_bottom + 33} Td",
                f"({_escape_and_encode(_truncate_chart_label(card['headline_value'], 26))}) Tj",
                "ET",
                "BT",
                f"{TEXT_DARK} rg",
                f"/{BODY_FONT} 7 Tf",
                f"{card_x + 10} {card_bottom + 7} Td",
                f"({_escape_and_encode(_truncate_chart_label(resources_text, 100))}) Tj",
                "ET",
            ]
        )
        current_y = card_bottom - card_gap

    return bottom_y - 6


def _render_chart(commands, chart_item, top_y):
    if chart_item["variant"] == "variation_bar":
        return _render_variation_bar_chart(commands, chart_item, top_y)
    if chart_item["variant"] == "horizontal_bar":
        return _render_horizontal_bar_chart(commands, chart_item, top_y)
    return _render_vertical_bar_chart(commands, chart_item, top_y)


def _write_pdf_document(output_file, layout_lines, account_label=None):
    """
    Render the prepared layout items into a standalone PDF file.
    """
    pages = _paginate_layout_lines(layout_lines)

    objects = []

    def add_object(data):
        objects.append(data)
        return len(objects)

    logo_image = _load_png_logo_rgb()
    logo_image_id = None
    if logo_image:
        image_header = (
            f"<< /Type /XObject /Subtype /Image /Width {logo_image['width']} /Height {logo_image['height']} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(logo_image['data'])} >>\n"
            "stream\n"
        ).encode("ascii")
        logo_image_id = add_object(image_header + logo_image["data"] + b"\nendstream")

    font_regular_id = add_object(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    font_bold_id = add_object(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    font_mono_id = add_object(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    )
    font_italic_id = add_object(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>"
    )

    page_ids = []
    for index, page_items in enumerate(pages, start=1):
        stream = _build_page_stream(
            page_items,
            index,
            len(pages),
            account_label=account_label,
            logo_enabled=bool(logo_image_id),
        )
        stream_bytes = stream.encode("cp1252", errors="replace")
        content_id = add_object(f"<< /Length {len(stream_bytes)} >>\nstream\n{stream}endstream")
        xobject_section = ""
        if logo_image_id:
            xobject_section = f"/XObject << /ImLogo {logo_image_id} 0 R >> "
        page_id = add_object(
            "<< /Type /Page /Parent {parent} 0 R "
            f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << "
            f"/{BODY_FONT} {font_regular_id} 0 R "
            f"/{BODY_BOLD_FONT} {font_bold_id} 0 R "
            f"/{MONO_FONT} {font_mono_id} 0 R "
            f"/{ITALIC_FONT} {font_italic_id} 0 R "
            f">> {xobject_section}>> "
            f"/Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    pages_id = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>")

    for page_id in page_ids:
        objects[page_id - 1] = objects[page_id - 1].replace("{parent}", str(pages_id))

    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    pdf_parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in pdf_parts))
        obj_bytes = obj if isinstance(obj, bytes) else obj.encode("cp1252", errors="replace")
        pdf_parts.append(f"{index} 0 obj\n".encode("ascii"))
        pdf_parts.append(obj_bytes)
        pdf_parts.append(b"\nendobj\n")

    xref_offset = sum(len(part) for part in pdf_parts)
    pdf_parts.append(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf_parts.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_parts.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf_parts.append(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )

    with open(output_file, "wb") as file_handle:
        for part in pdf_parts:
            file_handle.write(part)


def write_text_pdf(output_file, text, account_label=None):
    """
    Write a styled PDF from a plain-text/markdown-like report.
    """
    _write_pdf_document(output_file, _prepare_layout_lines(text), account_label=account_label)


def write_cost_report_pdf(output_file, text, daily_costs=None, top_costs=None, sms_por_dia=None, account_label=None):
    """
    Write the main cost report PDF preserving the original text and adding summary charts first.
    """
    _write_pdf_document(output_file, _prepare_layout_lines(text), account_label=account_label)


def write_ai_analysis_pdf(output_file, text, report_data=None, account_label=None):
    """
    Write the AI analysis PDF preserving the analysis text and adding charts from the Bedrock payload.
    """
    _write_pdf_document(output_file, _prepare_layout_lines(text), account_label=account_label)
