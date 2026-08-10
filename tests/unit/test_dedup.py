"""Tests de deduplicación — la identidad es la URL, no el título."""

import pytest
from app.parsing import compute_dedup_hash

pytestmark = pytest.mark.unit


class TestDedupHash:

    def test_same_url_same_hash(self):
        """Misma URL → mismo hash, aunque el título sea diferente."""
        h1 = compute_dedup_hash("https://linkedin.com/jobs/123", "Engineer", "Google")
        h2 = compute_dedup_hash("https://linkedin.com/jobs/123", "Developer", "Meta")
        assert h1 == h2

    def test_different_url_different_hash(self):
        """URLs diferentes → hashes diferentes, aunque el título sea igual."""
        h1 = compute_dedup_hash("https://linkedin.com/jobs/123", "Engineer", "Google")
        h2 = compute_dedup_hash("https://linkedin.com/jobs/456", "Engineer", "Google")
        assert h1 != h2

    def test_trailing_slash_normalized(self):
        """URL con y sin trailing slash → mismo hash."""
        h1 = compute_dedup_hash("https://linkedin.com/jobs/123/", "Engineer", "Google")
        h2 = compute_dedup_hash("https://linkedin.com/jobs/123", "Engineer", "Google")
        assert h1 == h2

    def test_no_url_uses_title_company(self):
        """Sin URL → usa title + company como identidad."""
        h1 = compute_dedup_hash(None, "Engineer", "Google")
        h2 = compute_dedup_hash(None, "Engineer", "Google")
        assert h1 == h2

    def test_no_url_different_company(self):
        """Sin URL, misma posición, diferente empresa → hashes diferentes."""
        h1 = compute_dedup_hash(None, "Engineer", "Google")
        h2 = compute_dedup_hash(None, "Engineer", "Meta")
        assert h1 != h2

    def test_same_title_different_url_are_different_jobs(self):
        """'OpenStack Engineer' en dos URLs diferentes son DOS jobs."""
        h1 = compute_dedup_hash("https://spectraforce.com/job/1", "OpenStack Engineer", "SPECTRAFORCE")
        h2 = compute_dedup_hash("https://linkedin.com/jobs/999", "OpenStack Engineer", "SPECTRAFORCE CR")
        assert h1 != h2
