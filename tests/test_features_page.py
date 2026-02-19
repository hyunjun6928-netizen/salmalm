"""Tests for the features guide page API endpoints."""
import json
import pytest


def _make_handler():
    """Create a minimal mock handler to test API methods."""
    import sys, types
    # Import the web module
    sys.path.insert(0, '/tmp/salmalm')
    from salmalm.web import WebHandler

    class FakeHandler(WebHandler):
        def __init__(self):
            self._response_data = None
            self._status = 200

        def _json(self, data, status=200):
            self._response_data = data
            self._status = status

    return FakeHandler()


class TestFeaturesAPI:
    def test_features_returns_categories(self):
        h = _make_handler()
        h._get_features()
        assert "categories" in h._response_data

    def test_features_category_count(self):
        h = _make_handler()
        h._get_features()
        cats = h._response_data["categories"]
        assert len(cats) >= 7, f"Expected at least 7 categories, got {len(cats)}"

    def test_features_category_structure(self):
        h = _make_handler()
        h._get_features()
        cat = h._response_data["categories"][0]
        assert "id" in cat
        assert "icon" in cat
        assert "title" in cat
        assert "title_kr" in cat
        assert "features" in cat

    def test_features_feature_structure(self):
        h = _make_handler()
        h._get_features()
        feat = h._response_data["categories"][0]["features"][0]
        assert "name" in feat
        assert "desc" in feat

    def test_features_i18n_keys_exist(self):
        h = _make_handler()
        h._get_features()
        for cat in h._response_data["categories"]:
            assert "title_kr" in cat, f"Missing title_kr in category {cat['id']}"
            for f in cat["features"]:
                if f["name"].startswith("/"):
                    assert "desc_kr" in f, f"Missing desc_kr for command {f['name']}"
                else:
                    assert "name_kr" in f or f["name"].startswith("/"), f"Missing name_kr for {f['name']}"

    def test_features_min_feature_count(self):
        h = _make_handler()
        h._get_features()
        total = sum(len(c["features"]) for c in h._response_data["categories"])
        assert total >= 35, f"Expected at least 35 features, got {total}"

    def test_tools_list_response(self):
        h = _make_handler()
        h._get_tools_list()
        assert "tools" in h._response_data
        assert "count" in h._response_data
        assert isinstance(h._response_data["tools"], list)
        assert h._response_data["count"] >= 1

    def test_commands_response(self):
        h = _make_handler()
        h._get_commands()
        assert "commands" in h._response_data
        assert "count" in h._response_data
        cmds = h._response_data["commands"]
        assert len(cmds) >= 20
        # Check structure
        for c in cmds:
            assert "name" in c
            assert "desc" in c
            assert c["name"].startswith("/")

    def test_commands_no_duplicates(self):
        h = _make_handler()
        h._get_commands()
        names = [c["name"] for c in h._response_data["commands"]]
        assert len(names) == len(set(names)), "Duplicate commands found"

    def test_features_commands_category_has_slash_commands(self):
        h = _make_handler()
        h._get_features()
        cmd_cat = [c for c in h._response_data["categories"] if c["id"] == "commands"]
        assert len(cmd_cat) == 1
        for f in cmd_cat[0]["features"]:
            assert f["name"].startswith("/"), f"Command {f['name']} should start with /"
