"""Invariantes del GROUP_REGISTRY: el registry en código es la fuente de
canales y debe mantenerse alineado con el motor de parsers.

Probar estos invariantes evita que un grupo nuevo rompa la ingesta en silencio.
"""

import pytest

from app.parsing import PARSERS
from app.registry import GROUP_REGISTRY

pytestmark = pytest.mark.unit

REQUIRED_CATEGORY_KEYS = {
    "label",
    "search_keywords",
    "groups",
    "admin_alert_email",
    "demand_score",
    "last_polled",
    "poll_interval_hours",
}

REQUIRED_GROUP_KEYS = {
    "id",
    "name",
    "telegram_channel",
    "priority",
    "format_template",
    "status",
    "last_success",
    "consecutive_failures",
}

VALID_STATUSES = {"active", "down", "degraded"}


def test_registry_is_not_empty():
    assert GROUP_REGISTRY


def test_every_category_has_required_shape():
    for cat_id, cat in GROUP_REGISTRY.items():
        assert REQUIRED_CATEGORY_KEYS <= set(cat), cat_id
        assert isinstance(cat["search_keywords"], list), cat_id
        assert isinstance(cat["groups"], list) and cat["groups"], cat_id


def test_every_group_has_required_keys_and_non_empty_channel():
    for cat_id, cat in GROUP_REGISTRY.items():
        for group in cat["groups"]:
            label = f"{cat_id}:{group.get('id')}"
            assert REQUIRED_GROUP_KEYS <= set(group), label
            assert group["telegram_channel"], label


def test_group_ids_are_unique_globally():
    ids = [g["id"] for cat in GROUP_REGISTRY.values() for g in cat["groups"]]
    assert len(ids) == len(set(ids))


def test_priorities_are_unique_within_category():
    for cat_id, cat in GROUP_REGISTRY.items():
        priorities = [g["priority"] for g in cat["groups"]]
        assert len(priorities) == len(set(priorities)), cat_id


def test_group_statuses_are_valid():
    for cat in GROUP_REGISTRY.values():
        for group in cat["groups"]:
            assert group["status"] in VALID_STATUSES, group["id"]


@pytest.mark.parametrize(
    "cat_id,cat",
    [(k, v) for k, v in GROUP_REGISTRY.items()],
    ids=list(GROUP_REGISTRY),
)
def test_every_format_template_exists_in_parser_engine(cat_id, cat):
    for group in cat["groups"]:
        assert group["format_template"] in PARSERS, f"{cat_id}:{group['id']}"