"""Reglas de negocio de ingesta: intervalos de demanda y categoría inferida.

Comportamiento bajo prueba (público):
- get_poll_interval: escala de demanda -> frecuencia de polling, con soporte
  de intervalos custom por categoría desde GROUP_REGISTRY.
- infer_category: ruteo por keywords y luego por ubicación (search_keywords),
  con fallback a stem_cr para entradas vacías o desconocidas.
"""

import pytest

from app.ingestion import DEMAND_TIERS, get_poll_interval, infer_category

pytestmark = pytest.mark.unit


class TestDemandTiers:

    def test_tiers_are_contiguous_from_zero(self):
        lows = [low for low, _, _ in DEMAND_TIERS]
        assert lows[0] == 0
        assert lows == sorted(lows)

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0, 24), (4, 24),
            (5, 12), (19, 12),
            (20, 6), (49, 6),
            (50, 3), (998, 3),
            (999, 24),
            (10_000, 24),
        ],
    )
    def test_interval_for_demand_score(self, score, expected):
        assert get_poll_interval(score, "unknown_category") == expected

    def test_custom_interval_from_registry(self):
        # from_work_home define poll_interval_hours explícito (48)
        assert get_poll_interval(0, "from_work_home") == 48

    def test_default_category_interval_is_24(self):
        assert get_poll_interval(0, "stem_cr") == 24


class TestInferCategory:

    def test_infers_by_keyword(self):
        assert infer_category("Software Developer", "") == "stem_cr"

    def test_infers_remote_keyword_to_latam(self):
        assert infer_category("Remote Support Specialist", "") == "latam_remote"

    def test_infers_by_costa_rica_location(self):
        assert infer_category("", "San José, Costa Rica") == "stem_cr"

    def test_infers_by_heredia_location(self):
        assert infer_category("", "Heredia, CR") == "stem_cr"

    def test_infers_by_denmark_location(self):
        assert infer_category("", "Copenhagen, Denmark") == "stem_dk"

    def test_empty_input_falls_back(self):
        assert infer_category("", "") == "stem_cr"

    def test_unknown_input_falls_back(self):
        assert infer_category("Pizza Chef", "Mars") == "stem_cr"

    def test_keyword_wins_over_location(self):
        # "developer" (stem_cr) aparece antes que "remote" (latam) en el orden
        assert infer_category("remote developer", "Copenhagen") == "stem_cr"