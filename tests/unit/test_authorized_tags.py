import pytest

from app.validation.tags import TagAuthorizer, UnauthorizedTagError


def test_closed_catalogue_has_exactly_78_tags_in_three_groups(config):
    assert len(config.authorized_tags) == 78
    assert len(set(config.authorized_tags)) == 78
    assert {group.group_id for group in config.server_groups} == {"COGCGPRO12", "COGCGPRO34", "COGCGPRO56"}
    for group in config.server_groups:
        assert len([tag for tag in config.authorized_tags if tag.startswith(group.pi_prefix)]) == 26


def test_authorizer_rejects_unknown_tag_before_client_call(config):
    authorizer = TagAuthorizer(config)
    with pytest.raises(UnauthorizedTagError):
        authorizer.validate(["CSEO.COGCGPRO12.E3Run.NotAuthorized"])


def test_authorizer_rejects_duplicate_requests(config):
    authorizer = TagAuthorizer(config)
    tag = config.authorized_tags[0]
    with pytest.raises(ValueError, match="duplicate"):
        authorizer.validate([tag, tag])
