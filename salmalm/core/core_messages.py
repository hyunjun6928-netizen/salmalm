"""Message operations: search, edit, delete."""

import json
import logging

log = logging.getLogger(__name__)


def _get_db():
    """Lazy import to avoid circular dependency."""
    from salmalm.core.core import _get_db as _db

    return _db()


def edit_message(session_id: str, message_index: int, new_content: str) -> dict:
    """Edit a message at the given index in a session.

    Backs up the original messages first, then replaces the content.
    Returns {'ok': True, 'index': int} or {'ok': False, 'error': ...}.
    """
    session = get_session(session_id)
    if message_index < 0 or message_index >= len(session.messages):
        return {"ok": False, "error": f"Invalid message_index: {message_index}"}
    msg = session.messages[message_index]
    if msg.get("role") != "user":
        return {"ok": False, "error": "Can only edit user messages"}
    # Backup current state
    conn = _get_db()
    conn.execute(
        "INSERT INTO session_message_backup (session_id, messages_json, removed_at, reason) VALUES (?,?,?,?)",
        (
            session_id,
            json.dumps(session.messages, ensure_ascii=False),
            datetime.now(KST).isoformat(),
            "edit",
        ),
    )  # noqa: F405
    conn.commit()
    # Update the message content
    session.messages[message_index]["content"] = new_content
    # Remove all messages after this index (assistant response will be regenerated)
    removed_count = len(session.messages) - message_index - 1
    session.messages = session.messages[: message_index + 1]
    session._persist()
    try:
        save_session_to_disk(session_id)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    audit_log(
        "message_edit",
        f"{session_id}: edited index {message_index}, removed {removed_count} subsequent",
        session_id=session_id,
    )
    return {"ok": True, "index": message_index, "removed_after": removed_count}


def delete_message(session_id: str, message_index: int) -> dict:
    """Delete a user message and its paired assistant response.

    Backs up removed messages to session_message_backup table.
    Returns {'ok': True, 'removed': int} or {'ok': False, 'error': ...}.
    """
    session = get_session(session_id)
    if message_index < 0 or message_index >= len(session.messages):
        return {"ok": False, "error": f"Invalid message_index: {message_index}"}
    msg = session.messages[message_index]
    if msg.get("role") != "user":
        return {"ok": False, "error": "Can only delete user messages"}
    indices_to_remove = [message_index]
    # Also remove the paired assistant message (next one if it's assistant)
    if message_index + 1 < len(session.messages) and session.messages[message_index + 1].get("role") == "assistant":
        indices_to_remove.append(message_index + 1)
    # Backup
    removed_msgs = [session.messages[i] for i in indices_to_remove]
    conn = _get_db()
    conn.execute(
        "INSERT INTO session_message_backup (session_id, messages_json, removed_at, reason) VALUES (?,?,?,?)",
        (
            session_id,
            json.dumps(removed_msgs, ensure_ascii=False),
            datetime.now(KST).isoformat(),
            "delete",
        ),
    )  # noqa: F405
    conn.commit()
    # Remove in reverse order
    for i in sorted(indices_to_remove, reverse=True):
        session.messages.pop(i)
    session._persist()
    try:
        save_session_to_disk(session_id)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    audit_log(
        "message_delete",
        f"{session_id}: deleted {len(indices_to_remove)} messages at index {message_index}",
        session_id=session_id,
    )
    return {"ok": True, "removed": len(indices_to_remove)}


def search_messages(query: str, limit: int = 20) -> list:
    """Search messages across all sessions using LIKE matching.

    Returns list of {'session_id', 'role', 'content', 'match_snippet', 'updated_at'}.
    """
    if not query or len(query.strip()) < 2:
        return []
    query = query.strip()
    results = []
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT session_id, messages, updated_at FROM session_store ORDER BY updated_at DESC"
        ).fetchall()
        for sid, msgs_json, updated_at in rows:
            try:
                msgs = json.loads(msgs_json)
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
            for msg in msgs:
                role = msg.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                content = _msg_content_str(msg)
                if query.lower() in content.lower():
                    # Extract snippet around the match
                    idx = content.lower().index(query.lower())
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(query) + 40)
                    snippet = ("..." if start > 0 else "") + content[start:end] + ("..." if end < len(content) else "")
                    results.append(
                        {
                            "session_id": sid,
                            "role": role,
                            "content": content[:200],
                            "match_snippet": snippet,
                            "updated_at": updated_at,
                        }
                    )
                    if len(results) >= limit:
                        return results
    except Exception as e:
        log.warning(f"search_messages error: {e}")
    return results
