"""Transcript Hygiene — provider-specific session history sanitization.

Cleans LLM conversation history before API calls. Applied in-memory only;
original history is never modified.
"""
import copy
import re
import secrets
from typing import Dict, List

from salmalm import log

# ── Provider Rules ───────────────────────────────────────────

PROVIDER_RULES: Dict[str, dict] = {
    'anthropic': {
        'merge_consecutive_user': True,
        'tool_result_pairing': True,
        'synthetic_tool_result': True,
    },
    'google': {
        'sanitize_tool_ids': True,
        'turn_alternation': True,
        'prepend_user_bootstrap': True,
    },
    'openai': {
        'image_sanitize_only': True,
    },
    'mistral': {
        'tool_id_length_9': True,
    },
}


class TranscriptHygiene:
    """Clean conversation history per provider rules before LLM API calls."""

    def __init__(self, provider: str = 'anthropic'):
        self.provider = provider.lower()
        self.rules = PROVIDER_RULES.get(self.provider, {})

    def clean(self, messages: List[dict]) -> List[dict]:
        """Return a sanitized copy of messages. Original is never modified."""
        msgs = copy.deepcopy(messages)

        # Universal repairs first
        msgs = self._remove_empty_assistant(msgs)
        msgs = self._repair_tool_calls(msgs)
        msgs = self._sanitize_images(msgs)

        # Provider-specific
        if self.rules.get('merge_consecutive_user'):
            msgs = self._merge_consecutive_user(msgs)
        if self.rules.get('tool_result_pairing'):
            msgs = self._fix_tool_result_pairing(msgs)
        if self.rules.get('synthetic_tool_result'):
            msgs = self._add_synthetic_tool_results(msgs)
        if self.rules.get('sanitize_tool_ids'):
            msgs = self._sanitize_tool_ids(msgs)
        if self.rules.get('turn_alternation'):
            msgs = self._enforce_turn_alternation(msgs)
        if self.rules.get('prepend_user_bootstrap'):
            msgs = self._prepend_user_bootstrap(msgs)
        if self.rules.get('tool_id_length_9'):
            msgs = self._tool_id_length_9(msgs)

        return msgs

    # ── Universal Repairs ────────────────────────────────────

    def _remove_empty_assistant(self, msgs: List[dict]) -> List[dict]:
        """Remove assistant messages with no content."""
        result = []
        for m in msgs:
            if m.get('role') == 'assistant':
                content = m.get('content', '')
                if isinstance(content, str) and not content.strip():
                    continue
                if isinstance(content, list) and not content:
                    continue
            result.append(m)
        return result

    def _repair_tool_calls(self, msgs: List[dict]) -> List[dict]:
        """Drop tool_use blocks with missing/invalid input."""
        result = []
        for m in msgs:
            if m.get('role') == 'assistant' and isinstance(m.get('content'), list):
                cleaned_content = []
                for block in m['content']:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        if 'input' not in block or not isinstance(block.get('input'), dict):
                            log.info(f'Dropping invalid tool_use: {block.get("id", "?")}')
                            continue
                    cleaned_content.append(block)
                if cleaned_content:
                    m['content'] = cleaned_content
                    result.append(m)
                # If all content was dropped, skip message
            else:
                result.append(m)
        return result

    def _sanitize_images(self, msgs: List[dict]) -> List[dict]:
        """Flag oversized base64 images (>1MB)."""
        SIZE_LIMIT = 1_000_000  # 1MB in base64 chars (approx)
        for m in msgs:
            content = m.get('content', '')
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        source = block.get('source', {})
                        if isinstance(source, dict) and source.get('type') == 'base64':
                            data = source.get('data', '')
                            if len(data) > SIZE_LIMIT:
                                log.info(f'Warning: oversized image ({len(data)} chars) in message')
                                # Can't resize without Pillow; just log
        return msgs

    # ── Anthropic ────────────────────────────────────────────

    def _merge_consecutive_user(self, msgs: List[dict]) -> List[dict]:
        """Merge consecutive user messages into one."""
        if not msgs:
            return msgs
        result = [msgs[0]]
        for m in msgs[1:]:
            if m.get('role') == 'user' and result[-1].get('role') == 'user':
                prev = result[-1]
                prev_content = prev.get('content', '')
                new_content = m.get('content', '')
                if isinstance(prev_content, str) and isinstance(new_content, str):
                    prev['content'] = prev_content + '\n' + new_content
                elif isinstance(prev_content, list) and isinstance(new_content, list):
                    prev['content'] = prev_content + new_content
                elif isinstance(prev_content, str) and isinstance(new_content, list):
                    prev['content'] = [{'type': 'text', 'text': prev_content}] + new_content
                elif isinstance(prev_content, list) and isinstance(new_content, str):
                    prev['content'] = prev_content + [{'type': 'text', 'text': new_content}]
            else:
                result.append(m)
        return result

    def _fix_tool_result_pairing(self, msgs: List[dict]) -> List[dict]:
        """Remove orphan tool_result messages (no matching tool_use)."""
        # Collect all tool_use IDs
        tool_use_ids = set()
        for m in msgs:
            if m.get('role') == 'assistant' and isinstance(m.get('content'), list):
                for block in m['content']:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        tid = block.get('id')
                        if tid:
                            tool_use_ids.add(tid)

        # Filter tool_result messages
        result = []
        for m in msgs:
            if m.get('role') == 'user' and isinstance(m.get('content'), list):
                filtered = []
                for block in m['content']:
                    if isinstance(block, dict) and block.get('type') == 'tool_result':
                        if block.get('tool_use_id') not in tool_use_ids:
                            log.info(f'Removing orphan tool_result: {block.get("tool_use_id")}')
                            continue
                    filtered.append(block)
                if filtered:
                    m['content'] = filtered
                    result.append(m)
            else:
                result.append(m)
        return result

    def _add_synthetic_tool_results(self, msgs: List[dict]) -> List[dict]:
        """Add synthetic tool_result for unmatched tool_use blocks."""
        # Collect tool_result IDs
        result_ids = set()
        for m in msgs:
            if isinstance(m.get('content'), list):
                for block in m['content']:
                    if isinstance(block, dict) and block.get('type') == 'tool_result':
                        result_ids.add(block.get('tool_use_id'))

        # Find unmatched tool_use
        result = []
        for i, m in enumerate(msgs):
            result.append(m)
            if m.get('role') == 'assistant' and isinstance(m.get('content'), list):
                unmatched = []
                for block in m['content']:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        tid = block.get('id')
                        if tid and tid not in result_ids:
                            unmatched.append(tid)
                if unmatched:
                    # Check if next message is a user message with tool_results
                    needs_synthetic = True
                    if i + 1 < len(msgs):
                        next_m = msgs[i + 1]
                        if next_m.get('role') == 'user' and isinstance(next_m.get('content'), list):
                            needs_synthetic = False
                    if needs_synthetic:
                        synthetic_content = [
                            {'type': 'tool_result', 'tool_use_id': tid, 'content': '(no result)'}
                            for tid in unmatched
                        ]
                        result.append({'role': 'user', 'content': synthetic_content})
        return result

    # ── Google ───────────────────────────────────────────────

    def _sanitize_tool_ids(self, msgs: List[dict]) -> List[dict]:
        """Ensure tool IDs contain only alphanumeric characters."""
        id_map = {}
        for m in msgs:
            if isinstance(m.get('content'), list):
                for block in m['content']:
                    if isinstance(block, dict):
                        for key in ('id', 'tool_use_id'):
                            old_id = block.get(key)
                            if old_id and not re.match(r'^[a-zA-Z0-9_]+$', old_id):
                                if old_id not in id_map:
                                    id_map[old_id] = re.sub(r'[^a-zA-Z0-9_]', '', old_id) or secrets.token_hex(4)
                                block[key] = id_map[old_id]
        return msgs

    def _enforce_turn_alternation(self, msgs: List[dict]) -> List[dict]:
        """Ensure strict user/assistant turn alternation for Google."""
        if not msgs:
            return msgs
        result = [msgs[0]]
        for m in msgs[1:]:
            if m.get('role') == result[-1].get('role'):
                # Same role consecutive — merge
                prev = result[-1]
                pc = prev.get('content', '')
                nc = m.get('content', '')
                if isinstance(pc, str) and isinstance(nc, str):
                    prev['content'] = pc + '\n' + nc
                else:
                    # Convert to list and merge
                    def _to_list(c):
                        if isinstance(c, list):
                            return c
                        return [{'type': 'text', 'text': str(c)}]
                    prev['content'] = _to_list(pc) + _to_list(nc)
            else:
                result.append(m)
        return result

    def _prepend_user_bootstrap(self, msgs: List[dict]) -> List[dict]:
        """Prepend a user message if history starts with assistant."""
        if msgs and msgs[0].get('role') == 'assistant':
            return [{'role': 'user', 'content': '(start)'}] + msgs
        return msgs

    # ── Mistral ──────────────────────────────────────────────

    def _tool_id_length_9(self, msgs: List[dict]) -> List[dict]:
        """Ensure all tool call IDs are exactly 9 alphanumeric characters."""
        id_map = {}
        for m in msgs:
            if isinstance(m.get('content'), list):
                for block in m['content']:
                    if isinstance(block, dict):
                        for key in ('id', 'tool_use_id'):
                            old_id = block.get(key)
                            if old_id:
                                if old_id not in id_map:
                                    clean = re.sub(r'[^a-zA-Z0-9]', '', old_id)
                                    if len(clean) >= 9:
                                        id_map[old_id] = clean[:9]
                                    else:
                                        id_map[old_id] = (clean + secrets.token_hex(5))[:9]
                                block[key] = id_map[old_id]
        return msgs
