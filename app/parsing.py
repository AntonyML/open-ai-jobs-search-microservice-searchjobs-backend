import re
import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedJob:
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    salary: Optional[str] = None
    source_channel: str = ""
    source_message_id: int = 0
    raw_text: str = ""
    portal: Optional[str] = None
    tags: Optional[list[str]] = None


# ── Shared utilities ────────────────────────────────────────────────

URL_RE = re.compile(r"https?://\S+")
SALARY_RE = re.compile(
    r"\$?\d[\d.,]*\s*[–-]\s*\$?\d[\d.,]*(?:\s*(?:USD|EUR|CRC|DKK|mes|month|año|year|hr|hour))?",
    re.IGNORECASE,
)
EMOJI_CLEAN_RE = re.compile(r"[🧑‍💼💼🔥🚀📌🏢✅‼️🆕👉➡️🖼📢💻⚡🌟💡🔍✨🎯🔹⭐]\s*|[\U0001F300-\U0001FAFF]")
MARKDOWN_CLEAN_RE = re.compile(r"\*{1,2}\s*")


def clean_markdown(text: str) -> str:
    return MARKDOWN_CLEAN_RE.sub("", text).strip()


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = EMOJI_CLEAN_RE.sub("", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compute_dedup_hash(url: str | None, title: str, company: str | None) -> str:
    """
    La identidad de un job es su URL.
    Si no hay URL, fallback a title + company.
    """
    if url:
        # Normalizar URL: quitar trailing slash
        normalized = url.strip().rstrip("/")
        key = normalized
    else:
        # Sin URL: usar title + company como identidad
        key = f"{title.strip().lower()}|{(company or '').strip().lower()}"
    return hashlib.sha256(key.encode()).hexdigest()


def infer_portal_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url_lower = url.lower()
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "myworkdayjobs.com" in url_lower or "workday" in url_lower:
        return "workday"
    if "indeed.com" in url_lower:
        return "indeed"
    if "glassdoor.com" in url_lower:
        return "glassdoor"
    if "getonbrd.com" in url_lower:
        return "getonbrd"
    if "computrabajo.com" in url_lower:
        return "computrabajo"
    return "website"


# ═══════════════════════════════════════════════════════════════════
# STEM Jobs CR (stem_jobscr)
# ═══════════════════════════════════════════════════════════════════
# Formato:
# 🧑‍💼  |  <titulo>
# Empresa: <empresa>
# Ubicación: <ubicacion>
# Tags: #tag #tag        ← opcional
# <url>                  ← LinkedIn o Workday
# <nombre portal>
# <texto preview "Posted ...">

STEM_JOBSCR_RE = re.compile(
    r"(?:🧑‍💼|💼|🔥|🚀|📌|🏢|💻|⚡)\s*\|\s*(?P<title>[^\n]+?)\s*\n"
    r"(?:.*?Empresa:\s*(?P<company>[^\n]+)\s*\n)?"
    r"(?:.*?Categoría:\s*(?P<category>[^\n]+)\s*\n)?"
    r"(?:.*?Ubicaci[oó]n:\s*(?P<location>[^\n]+)\s*\n)?"
    r"(?:.*?Tags:\s*(?P<tags>[^\n]+)\s*\n)?"
    r"(?:.*?Salario:\s*(?P<salary>[^\n]+)\s*\n)?",
    re.IGNORECASE | re.MULTILINE,
)


def parse_stem_jobscr(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    m = STEM_JOBSCR_RE.search(text)
    if not m:
        return None

    title = clean_markdown(m.group("title").strip())
    if not title or len(title) < 3:
        return None

    company = clean_markdown(m.group("company").strip()) if m.group("company") else None
    location = clean_markdown(m.group("location").strip()) if m.group("location") else None
    tags_raw = m.group("tags")
    tags = [t.strip("#").strip() for t in tags_raw.split() if t.strip().startswith("#")] if tags_raw else None

    urls = URL_RE.findall(text)
    url = urls[0] if urls else None
    portal = infer_portal_from_url(url) or ("linkedin" if "linkedin.com" in text.lower() else None)

    # Extract salary from text if not in named group
    salary = clean_markdown(m.group("salary").strip()) if m.group("salary") else None
    if not salary:
        sal_match = SALARY_RE.search(text)
        if sal_match:
            salary = sal_match.group()

    return ParsedJob(
        title=title[:200],
        company=company,
        location=location,
        url=url,
        description=text[:800],
        salary=salary,
        tags=tags,
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
        portal=portal,
    )


# ═══════════════════════════════════════════════════════════════════
# IT Freelancers (it_freelancers)
# ═══════════════════════════════════════════════════════════════════
# Formato inglés:
# ‼️‼️🆕 <titulo>
# Skills: <skills>
# Position: <position>
# Salary: $2,000 – $5,000
# Contact: @handle
# <descripción>
#
# Variante ucraniana:
# ‼️‼️🆕 <titulo>
# 👉 Роль - <titulo>
# 👉 Компанія - <empresa>
# 👉 Зарплата: $3,500–5,000/місяць
# 👉 Контакти: @handle
# <descripción>

IT_FREELANCERS_RE = re.compile(
    r"‼️*‼️*🆕*\s*(?P<title>[^\n]+)",  # Title right after the emojis
    re.IGNORECASE,
)

SKILLS_RE = re.compile(r"Skills:\s*(?P<skills>.+?)(?:\n|$)", re.IGNORECASE)
POSITION_RE = re.compile(r"Position:\s*(?P<position>.+?)(?:\n|$)", re.IGNORECASE)
SALARY_LINE_RE = re.compile(
    r"(?:Salary|Зарплата|Salario):\s*(?P<salary>\$?[\d.,]+\s*[–-]\s*\$?[\d.,]+[^\n]*)",
    re.IGNORECASE,
)
CONTACT_RE = re.compile(r"Contact:\s*(?P<contact>@\w+)", re.IGNORECASE)
# Cyrillic markers
CYRILLIC_ROLE_RE = re.compile(r"Роль\s*[-–—]\s*(?P<title>[^\n]+)", re.IGNORECASE)
CYRILLIC_COMPANY_RE = re.compile(r"Компанія\s*[-–—]\s*(?P<company>[^\n]+)", re.IGNORECASE)
CYRILLIC_CONTACT_RE = re.compile(r"(?:Контакти|Contact)\s*[:]\s*(?P<contact>@\w+)", re.IGNORECASE)


def parse_it_freelancers(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    # Check if there's a 💼 emoji or ‼️🆕 pattern to indicate this is a job post
    has_job_signal = bool(re.search(r"‼️.*🆕|💼|Position:|Skills:|Роль\s*[-–—]", text))
    if not has_job_signal:
        return None

    title = None
    company = None
    salary = None
    contact = None
    skills_text = None

    # Try Cyrillic first
    cyr_role = CYRILLIC_ROLE_RE.search(text)
    cyr_company = CYRILLIC_COMPANY_RE.search(text)
    cyr_contact = CYRILLIC_CONTACT_RE.search(text)

    if cyr_role:
        title = clean_markdown(cyr_role.group("title").strip())
    else:
        # English format — try title after ‼️🆕
        title_match = IT_FREELANCERS_RE.search(text)
        if title_match:
            title = EMOJI_CLEAN_RE.sub("", title_match.group("title")).strip()
        # Fallback: try after "Position:"
        if not title or len(title) < 3:
            pos_match = POSITION_RE.search(text)
            if pos_match:
                title = pos_match.group("position").strip()

    if cyr_company:
        company = clean_markdown(cyr_company.group("company").strip())

    # Skills
    skills_match = SKILLS_RE.search(text)
    if skills_match:
        skills_text = skills_match.group("skills").strip()

    # Salary
    sal_match = SALARY_LINE_RE.search(text)
    if sal_match:
        salary = sal_match.group("salary").strip()
    if not salary:
        fallback_sal = SALARY_RE.search(text)
        if fallback_sal:
            salary = fallback_sal.group()

    # Contact
    if cyr_contact:
        contact = cyr_contact.group("contact").strip()
    cont_match = CONTACT_RE.search(text)
    if cont_match:
        contact = cont_match.group("contact").strip()

    if not title or len(title) < 3:
        return None

    # Build description from the rest of the text
    description = text[:800]

    return ParsedJob(
        title=title[:200],
        company=company,
        url=None,  # No external URL — it's a Telegram post
        description=description,
        salary=salary,
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
        portal="telegram",
    )


# ═══════════════════════════════════════════════════════════════════
# Vacantes Remotas (vacantes_remotas)
# ═══════════════════════════════════════════════════════════════════
# Formato:
# <empresa> busca <rol>
# ✅ 100% remoto para <ubicacion> con <beneficios>
# Más info aquí ➡️ <url>

VACANTES_REMOTAS_RE = re.compile(
    r"(?P<company>[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚñ\s&]+?)\s+busca\s+(?P<role>[^\n]+?)\s*\n"
    r"(?:.*?✅\s*(?P<line2>[^\n]+))?\s*\n?"
    r"(?:.*?Más\s*info\s*aquí\s*[➡️→]*\s*(?P<url>https?://\S+))?",
    re.IGNORECASE | re.DOTALL,
)

LINE2_LOCATION_RE = re.compile(r"remoto\s+para\s+(?P<location>[^,\n]+)")


def parse_vacantes_remotas(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    m = VACANTES_REMOTAS_RE.search(text)
    if not m:
        return None

    company = clean_markdown(m.group("company").strip()) if m.group("company") else None
    title = clean_markdown(m.group("role").strip()) if m.group("role") else None
    url = m.group("url").strip() if m.group("url") else None
    line2 = m.group("line2").strip() if m.group("line2") else None

    if not title or len(title) < 3:
        return None

    # Extract location from line2
    location = None
    if line2:
        loc_match = LINE2_LOCATION_RE.search(line2)
        if loc_match:
            location = loc_match.group("location").strip()

    # Extract salary from line2
    salary = None
    if line2:
        sal_match = SALARY_RE.search(line2)
        if sal_match:
            salary = sal_match.group()

    return ParsedJob(
        title=title[:200],
        company=company,
        location=location,
        url=url,
        description=line2 or text[:500],
        salary=salary,
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
        portal="vacantesremotas",
    )


# ═══════════════════════════════════════════════════════════════════
# From Work Home (from_work_home — con filtro de spam)
# ═══════════════════════════════════════════════════════════════════
# Este grupo es mayormente spam/gigs. Implementamos filtro de calidad.
# Señales de spam:
# - Links de referido (tglink.io, earn, referral)
# - "Download now", "no skills", "no investment"
# - Esquemas de pago-por-tarea
# - Posts solo con imagen 🖼
# - "Earn money", "make money fast", "UPI", "referral link"

SPAM_SIGNALS = [
    r"tglink\.io",
    r"tinyurl\.com",
    r"download\s+(now|the\s+app)",
    r"no\s+(skills|experience|investment|degree)",
    r"earn\s+(money|cash|[$₹])",
    r"make\s+money\s+(fast|online|from\s+home)",
    r"UPI\s+payment",
    r"referral\s+link",
    r"pay\s+(per\s+)?task",
    r"gift\s+card",
    r"crypto\s+(giveaway|airdrop)",
    r"click\s+here\s+to\s+(earn|win|get)",
    r"\byapple\b",
    r"earn\s+grams",
    r"withdraw.*(?:paytm|upi|phonepe)",
    r"daily\s+(earning|income|profit)",
    r"(?:work|job)\s+(from\s+)?home.*(?:data\s+entry|copy\s+paste)",
    r"part[- ]time.*(?:data\s+entry|typing)",
    r"🖼\s*$",  # Only an image emoji
]

SPAM_RE = re.compile("|".join(SPAM_SIGNALS), re.IGNORECASE)

# Señales de trabajo legítimo en from_work_home
LEGIT_SIGNALS = [
    r"(?:hiring|we\s+are\s+hiring|now\s+hiring|we\s+need)",
    r"(?:remote|remoto|home\s+office)\s*(?:developer|engineer|designer|writer|support|assistant)",
    r"(?:salary|wage|hourly|annual|compensation)",
    r"(?:full[- ]time|part[- ]time|contract|freelance)",
    r"(?:company|startup|agency|team)",
    r"(?:requirements|qualifications|skills needed)",
    r"(?:apply|send\s+resume|send\s+cv|submit\s+application)",
]


import structlog

_spam_logger = structlog.get_logger("app.parsing.spam_filter")


def _is_spam(text: str, channel: str, msg_id: int) -> bool:
    """Return True if the message contains spam signals."""
    is_spam = bool(SPAM_RE.search(text))
    if is_spam:
        match = SPAM_RE.search(text)
        _spam_logger.warning(
            "spam_discarded",
            channel=channel,
            msg_id=msg_id,
            reason=f"matched spam signal: {match.group() if match else 'unknown'}",
            preview=text[:100],
        )
    return is_spam


def _is_likely_legit(text: str) -> bool:
    """Return True if the message shows signals of a legitimate job."""
    return bool(re.search("|".join(LEGIT_SIGNALS), text, re.IGNORECASE))


def parse_from_work_home(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    """Parse a from_work_home message with spam filtering.

    Returns None for spam. Only parses legitimate-looking job posts as freetext.
    """
    # Spam filter — discard obvious spam
    if _is_spam(text, channel, msg_id):
        return None

    # If no legit signals, discard too
    if not _is_likely_legit(text):
        _spam_logger.info(
            "no_legit_signals_discarded",
            channel=channel,
            msg_id=msg_id,
            preview=text[:100],
        )
        return None

    # Parse as freetext
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return None

    title = EMOJI_CLEAN_RE.sub("", lines[0]).strip(" |#-")
    if not title or len(title) < 3:
        return None

    urls = URL_RE.findall(text)
    salary = None
    sal_match = SALARY_RE.search(text)
    if sal_match:
        salary = sal_match.group()

    company = None
    location = None

    for line in lines[1:]:
        low = line.lower()
        if any(w in low for w in ["empresa", "company", "compañía", "compania", "at ", " @"]):
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) > 1:
                company = parts[1].strip()
            elif "at " in low:
                at_idx = low.index("at ")
                company = line[at_idx + 3:].strip()
        elif any(w in low for w in ["ubicación", "location", "ubicacion", "lugar", "remoto"]):
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) > 1:
                location = parts[1].strip()

    return ParsedJob(
        title=title[:200],
        company=company,
        location=location,
        url=urls[0] if urls else None,
        description=text[:500],
        salary=salary,
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
        portal=infer_portal_from_url(urls[0] if urls else None) or "telegram",
    )


# ═══════════════════════════════════════════════════════════════════
# Legacy parsers (kept for backward compatibility)
# ═══════════════════════════════════════════════════════════════════

LINKEDIN_FORWARD_RE = re.compile(
    r"(?P<url>https://www\.linkedin\.com/jobs/view/\d+)\s*"
    r"(?:LinkedIn\s*)?"
    r"(?P<company>.+?)\s+hiring\s+(?P<title>.+?)\s+in\s+(?P<location>[^\n]+)"
    r"(?:\s*\|\s*LinkedIn)?",
    re.IGNORECASE | re.DOTALL,
)

STRUCTURED_EMOJI_RE = re.compile(
    r"[🧑‍💼💼🔥🚀📌🏢]\s*\|?\s*(?P<title>.+?)\n"
    r"(?:Empresa|Compañía|Company|Compania):\s*(?P<company>.+?)\n"
    r"(?:Ubicación|Location|Ubicacion):\s*(?P<location>.+?)\n"
    r"(?:(?:Salario|Salary|💰):\s*(?P<salary>.+?)\n)?"
    r"(?:(?P<url>https?://\S+))?",
    re.IGNORECASE,
)

STEM_LATAM_RE = re.compile(
    r"[🧑‍💼💼🔥🚀📌🏢]\s*\|\s*(?:\*{1,2}\s*)?(?P<title>[^\n]+?)(?:\s*\*{1,2})?\s*\n"
    r"(?:.*?(?:\*{1,2})?Empresa(?:\*{0,2})?:?\s*(?P<company>[^\n]+?)\s*\n)?"
    r"(?:.*?(?:\*{1,2})?Ubicaci[oó]n(?:\*{0,2})?:?\s*(?P<location>[^\n]+?)\s*\n)?"
    r"(?:.*?(?:\*{1,2})?Categor[ií]a(?:\*{0,2})?:?\s*(?P<category>[^\n]+?)\s*\n)?"
    r"(?:.*?(?:\*{1,2})?Salario(?:\*{0,2})?:?\s*(?P<salary>[^\n]+?)\s*\n)?",
    re.IGNORECASE | re.DOTALL,
)


def parse_stem_latam(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    m = STEM_LATAM_RE.search(text)
    if not m:
        return None

    title = clean_markdown(m.group("title").strip())
    if not title or len(title) < 3:
        return None

    company = clean_markdown(m.group("company").strip()) if m.group("company") else None
    location = clean_markdown(m.group("location").strip()) if m.group("location") else None
    urls = URL_RE.findall(text)

    return ParsedJob(
        title=title[:200],
        company=company,
        location=location,
        url=urls[0] if urls else None,
        description=text[:500],
        salary=clean_markdown(m.group("salary").strip()) if m.group("salary") else None,
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
        portal="linkedin" if "linkedin.com" in text.lower() else None,
    )


def parse_linkedin_forward(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    m = LINKEDIN_FORWARD_RE.search(text)
    if not m:
        return None
    return ParsedJob(
        title=m.group("title").strip(),
        company=m.group("company").strip(),
        location=m.group("location").strip(),
        url=m.group("url").strip(),
        description=text[:500],
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
        portal="linkedin",
    )


def parse_structured_emoji(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    m = STRUCTURED_EMOJI_RE.search(text)
    if not m:
        return None
    return ParsedJob(
        title=m.group("title").strip(),
        company=m.group("company").strip() if m.group("company") else None,
        location=m.group("location").strip() if m.group("location") else None,
        url=m.group("url").strip() if m.group("url") else None,
        salary=m.group("salary").strip() if m.group("salary") else None,
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
    )


def parse_freetext(text: str, channel: str, msg_id: int) -> Optional[ParsedJob]:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return None

    title = EMOJI_CLEAN_RE.sub("", lines[0]).strip(" |#-")
    if not title or len(title) < 3:
        return None

    urls = URL_RE.findall(text)
    salary = SALARY_RE.search(text)
    company = None
    location = None

    for line in lines[1:]:
        low = line.lower()
        if any(w in low for w in ["empresa", "company", "compañía", "compania"]):
            company = line.split(":", 1)[-1].strip()
        elif any(
            w in low for w in ["ubicación", "location", "ubicacion", "lugar", "lokalitet"]
        ):
            location = line.split(":", 1)[-1].strip()

    return ParsedJob(
        title=title[:200],
        company=company,
        location=location,
        url=urls[0] if urls else None,
        description=text[:500],
        salary=salary.group() if salary else None,
        source_channel=channel,
        source_message_id=msg_id,
        raw_text=text,
        portal="linkedin" if "linkedin.com" in text.lower() else None,
    )


# ═══════════════════════════════════════════════════════════════════
# Parser registry
# ═══════════════════════════════════════════════════════════════════

PARSERS = {
    "linkedin_forward": parse_linkedin_forward,
    "structured_emoji": parse_structured_emoji,
    "stem_latam": parse_stem_latam,
    "stem_jobscr": parse_stem_jobscr,
    "it_freelancers": parse_it_freelancers,
    "vacantes_remotas": parse_vacantes_remotas,
    "from_work_home": parse_from_work_home,
    "freetext": parse_freetext,
}


def parse_message(
    text: str, format_template: str, channel: str, msg_id: int
) -> Optional[ParsedJob]:
    parser = PARSERS.get(format_template, parse_freetext)
    try:
        result = parser(text, channel, msg_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Parser %s threw exception for msg %d in %s: %s",
            format_template, msg_id, channel, e,
        )
        result = None

    if result is None and format_template != "freetext":
        # Don't bypass spam filter: from_work_home returns None intentionally
        if format_template == "from_work_home":
            return None
        # Fallback to freetext for a best-effort parse
        try:
            result = parse_freetext(text, channel, msg_id)
        except Exception:
            result = None

    return result
