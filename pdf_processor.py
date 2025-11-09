import re
import pdfplumber
from typing import Dict, List, Tuple


# ========================================
# 0) REMOVE BAD CHARACTERS
# ========================================
BAD_CHARS = re.compile(
    r"[\u0000-\u001F\u007F-\u009F"        # control chars
    r"\uD800-\uDFFF"                      # surrogate halves
    r"\uE000-\uF8FF"                      # private-use unicode
    r"]"
)

def strip_bad_chars(text: str) -> str:
    return BAD_CHARS.sub("", text)


# ========================================
# 1) CLEAN BASIC PDF ARTIFACTS
# ========================================
def clean_text(text: str) -> str:
    replacements = {
        "\u201c": '"', "\u201d": '"',
        "\u2018": "'", "\u2019": "'",
        "\u2014": "-", "\u2013": "-",
        "\u00a0": " ", "\u200b": "", "\ufeff": "",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    # Replace weird bullets
    text = re.sub(r"[•●▪◦·■□★◆►▶]", " ", text)

    # Fix “linkedin . com”
    text = re.sub(r"(?i)\b([A-Za-z0-9\-]+)\s*\.\s*([A-Za-z0-9\-]+)\b", r"\1.\2", text)

    # Fix “https:// github”
    text = re.sub(r"(https?://)\s+", r"\1", text)

    # Fix “/ username”
    text = re.sub(r"/\s+([A-Za-z0-9])", r"/\1", text)

    # Normalize spaces and newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


# ========================================
# 2) SECTION HEADINGS (MASTER LIST)
# ========================================
HEADING_TOKENS = [
    "Education", "Experience", "Work Experience",
    "Projects", "Skills", "Technical Skills",
    "Honors", "Awards", "Achievements",
    "Certifications", "Publications"
]


# ========================================
# 3) FIX GLUED HEADINGS
# Example: "...coderEducationRCC" → "...coder\nEducation\nRCC"
# ========================================
def deglue_headings(text: str) -> str:
    headings = "|".join(re.escape(h) for h in HEADING_TOKENS)

    # Case 1 — Heading glued to next capital/number
    text = re.sub(
        rf"(?i)\b({headings})(?=[A-Z0-9])",
        r"\1\n",
        text
    )

    # Case 2 — Heading glued to previous token
    text = re.sub(
        rf"(?i)(?<!\n)\b({headings})\b",
        r"\n\1",
        text
    )

    # Case 3 — Remove junk like "Skills:" or "Honors /"
    text = re.sub(
        rf"(?i)\b({headings})\s*[:/\\\-]?\s*",
        r"\1\n",
        text
    )

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ========================================
# 4) SPLIT INTO SECTIONS
# ========================================
def split_sections(text: str) -> Dict[str, str]:
    pattern = "(" + "|".join(fr"\b{h}\b" for h in HEADING_TOKENS) + ")"
    parts = re.split(pattern, text, flags=re.IGNORECASE)

    if not parts:
        return {"Body": text}

    sections = {}

    # Header = text before 1st heading
    if parts[0].strip():
        sections["Header"] = parts[0].strip()

    # Process sections
    for i in range(1, len(parts), 2):
        heading = parts[i].strip().title()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""

        # Normalize
        if "Experience" in heading:
            heading = "Experience"
        elif "Education" in heading:
            heading = "Education"
        elif "Project" in heading:
            heading = "Projects"
        elif "Skill" in heading:
            heading = "Skills"
        elif any(x in heading for x in ["Honor", "Award", "Achievement"]):
            heading = "Honors"
        elif "Certification" in heading:
            heading = "Certifications"
        elif "Publication" in heading:
            heading = "Publications"

        if heading in sections:
            sections[heading] += "\n" + content
        else:
            sections[heading] = content

    return sections


# ========================================
# 5) TRIMMING HELPERS
# ========================================
def limit_lines(block: str, max_lines: int) -> str:
    lines = [l.strip() for l in block.split("\n") if l.strip()]
    return "\n".join(lines[:max_lines])


def limit_sentences(block: str, max_items: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", block)
    parts = [p.strip() for p in parts if p.strip()]
    return " ".join(parts[:max_items])


# ========================================
# 6) SECTION PRIORITY + LIMITS
# ========================================
SECTION_LIMITS = {
    "Header": (6, 6),
    "Skills": (10, 10),
    "Experience": (22, 18),
    "Projects": (20, 16),
    "Education": (12, 12),
    "Honors": (8, 6),
    "Certifications": (8, 6),
    "Publications": (8, 6),
}

SECTION_PRIORITY = [
    "Header", "Skills", "Experience", "Projects",
    "Education", "Honors", "Certifications", "Publications"
]


# ========================================
# 7) SHORTEN FOR LLM
# ========================================
def shorten_sections(sections: Dict[str, str], max_chars=6000) -> str:
    used = set()
    blocks = []

    # Priority pass
    for key in SECTION_PRIORITY:
        if key not in sections:
            continue
        used.add(key)

        block = sections[key]
        max_lines, max_sent = SECTION_LIMITS[key]

        block = limit_lines(block, max_lines)
        block = limit_sentences(block, max_sent)

        if key != "Header":
            block = f"{key}:\n{block}"

        blocks.append(block)

    # Add unknown leftover sections
    for key, val in sections.items():
        if key not in used and val.strip():
            blocks.append(f"{key}:\n{val.strip()}")

    final = "\n\n".join(blocks).strip()

    # Hard cap
    if len(final) > max_chars:
        final = final[:max_chars]
        cut = max(final.rfind("."), final.rfind("\n"))
        if cut > 0:
            final = final[:cut+1]

    return final


# ========================================
# 8) MAIN ENTRYPOINT
# ========================================
def extract_text_from_pdf(file_path: str) -> str:
    raw_pages = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            raw_pages.append(page.extract_text() or "")

    text = "\n".join(raw_pages)

    # ORDER IS IMPORTANT
    text = strip_bad_chars(text)
    text = clean_text(text)
    text = deglue_headings(text)
    sections = split_sections(text)
    final = shorten_sections(sections, max_chars=6000)

    print(final)
    return final
