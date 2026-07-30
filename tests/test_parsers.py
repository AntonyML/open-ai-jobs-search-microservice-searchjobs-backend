"""Tests de parsing con mensajes REALES de Telegram.
Escritos ANTES de arreglar los parsers — definen el comportamiento esperado.
"""

import pytest
from app.parsing import parse_message, parse_freetext

from tests.fixtures import (
    STEM_CR_1,
    STEM_CR_2,
    STEM_CR_3,
    STEM_LATAM_1,
    STEM_LATAM_2,
    VACANTES_1,
    VACANTES_2,
    ITFREELANCE_1,
    ITFREELANCE_2,
    WORKHOME_SPAM,
)


class TestSTEMCRParser:
    """Canal: STEMJobsCR — formato '🧑‍💼 | Title' + Empresa/Ubicación."""

    def test_extracts_title(self):
        result = parse_message(STEM_CR_1, "stem_jobscr", "STEMJobsCR", 1)
        assert result is not None
        assert result.title == "DevOps & Platform Engineer"

    def test_extracts_company(self):
        result = parse_message(STEM_CR_1, "stem_jobscr", "STEMJobsCR", 1)
        assert result is not None
        assert result.company == "GFT Group"

    def test_extracts_location(self):
        result = parse_message(STEM_CR_1, "stem_jobscr", "STEMJobsCR", 1)
        assert result is not None
        assert result.location is not None
        assert "Heredia" in result.location

    def test_extracts_url(self):
        result = parse_message(STEM_CR_1, "stem_jobscr", "STEMJobsCR", 1)
        assert result is not None
        assert result.url is not None
        assert result.url.startswith("https://")

    def test_location_with_remote(self):
        result = parse_message(STEM_CR_3, "stem_jobscr", "STEMJobsCR", 1)
        assert result is not None
        assert result.location is not None
        assert "Remote" in result.location

    def test_company_without_category_field(self):
        """Algunos mensajes tienen Categoría, otros no. Ambos deben funcionar."""
        result = parse_message(STEM_CR_2, "stem_jobscr", "STEMJobsCR", 1)
        assert result is not None
        assert result.company == "Abbott"
        assert result.location is not None
        assert "Costa Rica" in result.location


class TestSTEMLATAMParser:
    """Canal: STEMJobsLATAM — formato similar a CR."""

    def test_extracts_title(self):
        result = parse_message(STEM_LATAM_1, "stem_latam", "STEMJobsLATAM", 1)
        assert result is not None
        assert result.title == "Engineer II"

    def test_extracts_company(self):
        result = parse_message(STEM_LATAM_1, "stem_latam", "STEMJobsLATAM", 1)
        assert result is not None
        assert result.company == "Correlation One"

    def test_extracts_location(self):
        result = parse_message(STEM_LATAM_1, "stem_latam", "STEMJobsLATAM", 1)
        assert result is not None
        assert result.location is not None
        assert "Latin America" in result.location


class TestVacantesRemotasParser:
    """Canal: VacantesRemotas — formato 'X busca Y' + ✅ descripción."""

    def test_extracts_title(self):
        result = parse_message(VACANTES_1, "vacantes_remotas", "vacantesremotas", 1)
        assert result is not None
        assert "Asociado de Éxito del Cliente" in result.title

    def test_extracts_company(self):
        result = parse_message(VACANTES_1, "vacantes_remotas", "vacantesremotas", 1)
        assert result is not None
        assert result.company == "Vanta"

    def test_extracts_url(self):
        result = parse_message(VACANTES_1, "vacantes_remotas", "vacantesremotas", 1)
        assert result is not None
        assert result.url is not None
        assert "vacantesremotas.com" in result.url


class TestITFreelanceParser:
    """Canal: IT Freelance — formato libre con ‼️‼️🆕."""

    def test_extracts_title(self):
        result = parse_message(ITFREELANCE_1, "it_freelancers", "itfreelancers", 1)
        assert result is not None
        assert "Golang Developer" in result.title

    def test_extracts_salary(self):
        result = parse_message(ITFREELANCE_1, "it_freelancers", "itfreelancers", 1)
        assert result is not None
        assert result.salary is not None
        assert "2,000" in result.salary or "5,000" in result.salary

    def test_extracts_structured_fields(self):
        """Mensajes con emojis de sección (📍, 💼, 🌍) deben extraer location."""
        result = parse_message(ITFREELANCE_2, "it_freelancers", "itfreelancers", 1)
        assert result is not None
        assert "Technical Operations Specialist" in result.title


class TestSpamFilter:
    """Mensajes que NO son trabajos reales deben ser rechazados."""

    def test_rejects_spam(self):
        result = parse_message(WORKHOME_SPAM, "from_work_home", "from_work_home", 1)
        assert result is None
