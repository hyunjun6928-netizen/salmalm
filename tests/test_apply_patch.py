"""Tests for apply_patch tool."""
import pytest
from pathlib import Path
from salmalm.tools.tools_patch import apply_patch, _is_safe_path, _find_context_match


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


def test_add_file(workspace):
    patch = """*** Begin Patch
*** Add File: hello.txt
+line 1
+line 2
*** End Patch"""
    result = apply_patch(patch, str(workspace))
    assert '✅' in result
    assert (workspace / 'hello.txt').read_text() == 'line 1\nline 2\n'


def test_delete_file(workspace):
    (workspace / 'obsolete.txt').write_text('old')
    patch = """*** Begin Patch
*** Delete File: obsolete.txt
*** End Patch"""
    result = apply_patch(patch, str(workspace))
    assert '✅' in result
    assert not (workspace / 'obsolete.txt').exists()


def test_update_file(workspace):
    (workspace / 'app.py').write_text('line1\nold line\nline3\n')
    patch = """*** Begin Patch
*** Update File: app.py
@@
-old line
+new line
*** End Patch"""
    result = apply_patch(patch, str(workspace))
    assert '✅' in result
    content = (workspace / 'app.py').read_text()
    assert 'new line' in content
    assert 'old line' not in content


def test_path_traversal_blocked():
    safe, reason = _is_safe_path('../etc/passwd')
    assert not safe
    assert 'traversal' in reason.lower()


def test_binary_file_rejected():
    safe, reason = _is_safe_path('image.png')
    assert not safe
    assert 'Binary' in reason


def test_no_begin_patch():
    result = apply_patch('random text')
    assert '❌' in result


def test_context_match():
    lines = ['a', 'b', 'c', 'd']
    assert _find_context_match(lines, ['b', 'c']) == 1
    assert _find_context_match(lines, ['x']) == -1


def test_multi_operation(workspace):
    (workspace / 'existing.txt').write_text('hello\nworld\n')
    patch = """*** Begin Patch
*** Add File: new.txt
+new file content
*** Update File: existing.txt
@@
-hello
+goodbye
*** End Patch"""
    result = apply_patch(patch, str(workspace))
    assert result.count('✅') == 2
    assert (workspace / 'new.txt').exists()
    assert 'goodbye' in (workspace / 'existing.txt').read_text()


def test_delete_nonexistent(workspace):
    patch = """*** Begin Patch
*** Delete File: ghost.txt
*** End Patch"""
    result = apply_patch(patch, str(workspace))
    assert '⚠️' in result


def test_update_nonexistent(workspace):
    patch = """*** Begin Patch
*** Update File: nope.py
@@
-old
+new
*** End Patch"""
    result = apply_patch(patch, str(workspace))
    assert '❌' in result
