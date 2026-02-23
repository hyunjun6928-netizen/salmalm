"""Tests for mcp_marketplace.py — MCP marketplace."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from salmalm.features.mcp_marketplace import MCPMarketplace, MCP_CATALOG


class TestMCPCatalog:
    def test_catalog_not_empty(self):
        assert len(MCP_CATALOG) >= 8

    def test_catalog_entries_have_required_fields(self):
        for entry in MCP_CATALOG:
            assert 'name' in entry
            assert 'description' in entry
            assert 'command' in entry
            assert 'category' in entry


class TestMCPMarketplace:
    @pytest.fixture
    def mp(self, tmp_path):
        with patch('salmalm.features.mcp_marketplace._SERVERS_PATH', tmp_path / 'servers.json'), \
             patch('salmalm.features.mcp_marketplace._CONFIG_DIR', tmp_path):
            m = MCPMarketplace()
            yield m

    def test_list_empty(self, mp):
        result = mp.list_installed()
        assert 'No MCP servers' in result

    def test_catalog_display(self, mp):
        result = mp.catalog()
        assert 'Catalog' in result
        assert 'filesystem' in result

    def test_status_empty(self, mp):
        result = mp.status()
        assert '0/0' in result

    def test_search_found(self, mp):
        result = mp.search('github')
        assert 'github' in result.lower()

    def test_search_not_found(self, mp):
        result = mp.search('nonexistent_xyz')
        assert 'No MCP servers matching' in result

    def test_search_empty_query(self, mp):
        result = mp.search('')
        assert 'Usage' in result

    def test_install_no_params_needed(self, mp):
        with patch.object(mp, '_connect_server'):
            result = mp.install('memory')
            assert '✅' in result
            assert 'memory' in mp._installed

    def test_install_already_installed(self, mp):
        mp._installed['memory'] = {'name': 'memory'}
        result = mp.install('memory')
        assert 'already installed' in result

    def test_install_not_in_catalog(self, mp):
        result = mp.install('nonexistent')
        assert '❌' in result

    def test_install_needs_params(self, mp):
        result = mp.install('filesystem')
        assert '⚠️' in result or 'requires' in result

    def test_install_with_params(self, mp):
        with patch.object(mp, '_connect_server'):
            result = mp.install('filesystem', params={'path': '/tmp'})
            assert '✅' in result

    def test_remove(self, mp):
        mp._installed['memory'] = {'name': 'memory', 'command': [], 'status': 'installed'}
        with patch('salmalm.features.mcp_marketplace.MCPMarketplace._save'):
            result = mp.remove('memory')
            assert '🗑️' in result
            assert 'memory' not in mp._installed

    def test_remove_not_installed(self, mp):
        result = mp.remove('nothere')
        assert 'not installed' in result

    def test_get_catalog_json(self, mp):
        data = mp.get_catalog_json()
        assert isinstance(data, list)
        assert len(data) >= 8
        assert all('name' in d for d in data)

    def test_get_installed_json_empty(self, mp):
        data = mp.get_installed_json()
        assert data == []

    def test_get_installed_json_with_data(self, mp):
        mp._installed['memory'] = {
            'name': 'memory', 'description': 'test', 'category': 'memory',
            'status': 'connected', 'installed_at': 1000,
        }
        data = mp.get_installed_json()
        assert len(data) == 1
        assert data[0]['name'] == 'memory'
