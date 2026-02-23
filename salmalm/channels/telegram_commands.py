"""Telegram command handler — extracted from TelegramBot._handle_command."""

import os
import json
import asyncio
from pathlib import Path
from salmalm.security.crypto import vault, log
from salmalm.constants import DATA_DIR, VERSION, KST


class TelegramCommandsMixin:
    """Mixin for /command handling in Telegram bot."""

    async def _handle_command(self, chat_id, text: str, tenant_user=None):
        cmd = text.split()[0].lower()

        # Multi-tenant commands (available even when not registered)
        if cmd == "/register":
            from salmalm.features.users import user_manager

            if not user_manager.multi_tenant_enabled:
                self.send_message(chat_id, "멀티테넌트 모드가 비활성화되어 있습니다. / Multi-tenant mode is disabled.")
                return
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or len(parts[1].strip()) < 8:
                self.send_message(
                    chat_id, "❌ 사용법: /register <비밀번호> (8자 이상)\nUsage: /register <password> (8+ chars)"
                )
                return
            password = parts[1].strip()
            tg_username = ""  # Will be set from update context
            result = user_manager.register_telegram_user(str(chat_id), password, tg_username)
            if result["ok"]:
                self.send_message(
                    chat_id,
                    f"✅ 등록 완료! 사용자: {result['user']['username']}\n"
                    f"Registration complete! User: {result['user']['username']}",
                )
            else:
                self.send_message(chat_id, f"❌ {result['error']}")
            return

        if cmd == "/quota":
            from salmalm.features.users import user_manager

            if not user_manager.multi_tenant_enabled or not tenant_user:
                self.send_message(chat_id, "멀티테넌트 모드가 비활성화되어 있습니다.")
                return
            parts = text.split()
            # Admin: /quota set <user> <daily> <monthly>
            if len(parts) >= 5 and parts[1] == "set" and tenant_user.get("role") == "admin":
                target = user_manager.get_user_by_username(parts[2])
                if not target:
                    self.send_message(chat_id, f"❌ 사용자를 찾을 수 없습니다: {parts[2]}")
                    return
                try:
                    user_manager.set_quota(target["id"], daily_limit=float(parts[3]), monthly_limit=float(parts[4]))
                    self.send_message(chat_id, f"✅ {parts[2]} 쿼터 설정: 일 ${parts[3]}, 월 ${parts[4]}")
                except Exception as e:
                    self.send_message(chat_id, f"❌ {e}")
                return
            # Show own quota
            quota = user_manager.get_quota(tenant_user["id"])
            self.send_message(
                chat_id,
                f"📊 사용량 / Quota\n"
                f"  일일: ${quota.get('current_daily', 0):.2f} / ${quota.get('daily_limit', 5):.2f} "
                f"(남은: ${quota.get('daily_remaining', 0):.2f})\n"
                f"  월별: ${quota.get('current_monthly', 0):.2f} / ${quota.get('monthly_limit', 50):.2f} "
                f"(남은: ${quota.get('monthly_remaining', 0):.2f})",
            )
            return

        if cmd == "/user" and tenant_user and tenant_user.get("role") == "admin":
            from salmalm.features.users import user_manager
            from salmalm.web.auth import auth_manager

            parts = text.split()
            if len(parts) >= 3 and parts[1] == "create":
                username = parts[2]
                password = parts[3] if len(parts) > 3 else None
                if not password:
                    self.send_message(chat_id, "❌ /user create <username> <password>")
                    return
                try:
                    user = auth_manager.create_user(username, password, "user")
                    user_manager.ensure_quota(user["id"])
                    self.send_message(chat_id, f"✅ 사용자 생성: {username}")
                except ValueError as e:
                    self.send_message(chat_id, f"❌ {e}")
                return
            elif len(parts) >= 2 and parts[1] == "list":
                users = user_manager.get_all_users_with_stats()
                lines = ["👥 사용자 목록:"]
                for u in users:
                    status = "✅" if u["enabled"] else "⛔"
                    lines.append(f"  {status} {u['username']} ({u['role']}) - ${u.get('total_cost', 0):.2f}")
                self.send_message(chat_id, "\n".join(lines))
                return
            elif len(parts) >= 3 and parts[1] == "delete":
                ok = auth_manager.delete_user(parts[2])
                self.send_message(chat_id, f"{'✅ 삭제됨' if ok else '❌ 실패'}: {parts[2]}")
                return
            self.send_message(chat_id, "Usage: /user create|list|delete")
            return

        if cmd == "/start":
            self.send_message(chat_id, f"😈 {APP_NAME} v{VERSION} running\nready")  # noqa: F405
        elif cmd == "/usage":
            report = execute_tool("usage_report", {})
            self.send_message(chat_id, report)
        elif cmd == "/model":
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                choice = parts[1].strip()
                if choice == "auto":
                    router.set_force_model(None)
                    self.send_message(chat_id, "🤖 Auto routing enabled")
                else:
                    router.set_force_model(choice)
                    self.send_message(chat_id, f"🤖 Model fixed: {choice}")
            else:
                current = router.force_model or "auto"
                lines = [f"🤖 Current: {current}"]
                if not router.force_model:
                    tier_names = {1: "Simple (싼 모델)", 2: "Moderate (기본)", 3: "Complex (고급)"}
                    for tier_num, label in tier_names.items():
                        model = router._pick_available(tier_num)
                        lines.append(f"  {label}: {model.split('/')[-1]}")
                lines.append("")
                lines.append("/model <name> — fix model")
                lines.append("/model auto — auto routing")
                self.send_message(chat_id, "\n".join(lines))
        elif cmd == "/compact":
            session = get_session(f"telegram_{chat_id}")
            before = len(session.messages)
            session.messages = compact_messages(session.messages)
            self.send_message(chat_id, f"Compacted: {before} → {len(session.messages)} messages")
        elif cmd == "/clear":
            session = get_session(f"telegram_{chat_id}")
            session.messages = []
            session.add_system(build_system_prompt())
            self.send_message(chat_id, "🗑️ Chat cleared")
        elif cmd == "/tts":
            parts = text.split(maxsplit=1)
            session = get_session(f"telegram_{chat_id}")
            if len(parts) > 1 and parts[1].strip() in ("on", "off"):
                session.tts_enabled = parts[1].strip() == "on"
                status = "ON 🔊" if session.tts_enabled else "OFF 🔇"
                self.send_message(chat_id, f"TTS: {status}")
            else:
                status = "ON" if getattr(session, "tts_enabled", False) else "OFF"
                voice = getattr(session, "tts_voice", "alloy")
                self.send_message(
                    chat_id,
                    f"🔊 TTS: {status} (voice: {voice})\n/tts on · /tts off\n/voice alloy|nova|echo|fable|onyx|shimmer",
                )
        elif cmd == "/voice":
            parts = text.split(maxsplit=1)
            session = get_session(f"telegram_{chat_id}")
            valid_voices = ("alloy", "nova", "echo", "fable", "onyx", "shimmer")
            if len(parts) > 1 and parts[1].strip() in valid_voices:
                session.tts_voice = parts[1].strip()
                self.send_message(chat_id, f"🎙️ Voice: {session.tts_voice}")
            else:
                self.send_message(chat_id, f"Voices: {', '.join(valid_voices)}")
        elif cmd == "/help":
            self.send_message(
                chat_id,
                textwrap.dedent(f"""
                😈 {APP_NAME} v{VERSION}  # noqa: F405

                📋 **Assistant**
                /briefing — Daily briefing (날씨+일정+메일)
                /routine [morning|evening] — 루틴 실행
                /remind list — 리마인더 목록
                /remind delete <id> — 리마인더 삭제
                /tr <lang> <text> — 빠른 번역

                📝 **Notes & Knowledge**
                /note <content> — 메모 저장
                /note search <query> — 메모 검색
                /note list — 최근 메모
                /note tag <tag> <content> — 태그 메모

                💰 **Expenses**
                /expense add <desc> <amount> [cat] — 지출 기록
                /expense today — 오늘 지출
                /expense month [YYYY-MM] — 월별 요약

                🔖 **Links**
                /save <url> — 링크 저장
                /saved list — 저장 목록
                /saved search <query> — 검색

                🍅 **Pomodoro**
                /pomodoro start [min] — 집중 시작
                /pomodoro break [min] — 휴식
                /pomodoro stop — 중지

                📅 **Calendar & Email**
                /cal [today|week|month] — Calendar
                /mail [inbox|read|send|search] — Email

                ⚙️ **System**
                /usage — Token usage/cost
                /model [auto|...] — Model
                /compact — Compact conversation
                /clear — Clear conversation
                /tts [on|off] — Voice
                /help — This help
            """).strip(),
            )
        elif cmd == "/telegram":
            parts = text.split(maxsplit=2)
            if len(parts) >= 2 and parts[1] == "webhook":
                if len(parts) < 3:
                    self.send_message(chat_id, "❌ Usage: /telegram webhook <url>")
                    return
                url = parts[2].strip()
                result = self.set_webhook(url)
                if result.get("ok"):
                    self.send_message(chat_id, f"✅ Webhook set: {url}")
                else:
                    self.send_message(chat_id, f"❌ Webhook failed: {result}")
            elif len(parts) >= 2 and parts[1] == "polling":
                result = self.delete_webhook()
                self.send_message(chat_id, "✅ Switched to polling mode")
            else:
                mode = "webhook" if self._webhook_mode else "polling"
                self.send_message(chat_id, f"📡 Mode: {mode}\n/telegram webhook <url>\n/telegram polling")

        elif cmd in ("/cal", "/calendar"):
            parts = text.split(maxsplit=3)
            sub = parts[1] if len(parts) > 1 else "today"
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            if sub == "today":
                result = _exec_tool("calendar_list", {"period": "today"})
            elif sub == "week":
                result = _exec_tool("calendar_list", {"period": "week"})
            elif sub == "month":
                result = _exec_tool("calendar_list", {"period": "month"})
            elif sub == "add":
                # /cal add 2026-02-20 14:00 회의
                rest = parts[2] if len(parts) > 2 else ""
                cal_parts = rest.split(maxsplit=2)
                if len(cal_parts) < 2:
                    self.send_message(chat_id, "❌ Usage: /cal add YYYY-MM-DD HH:MM 제목")
                    return
                date_str = cal_parts[0]
                # Check if second part is time or title
                if ":" in cal_parts[1]:
                    time_str = cal_parts[1]
                    title = cal_parts[2] if len(cal_parts) > 2 else "Event"
                else:
                    time_str = ""
                    title = " ".join(cal_parts[1:])
                args = {"title": title, "date": date_str}
                if time_str:
                    args["time"] = time_str
                result = _exec_tool("calendar_add", args)
            elif sub == "delete":
                event_id = parts[2] if len(parts) > 2 else ""
                if not event_id:
                    self.send_message(chat_id, "❌ Usage: /cal delete <event_id>")
                    return
                result = _exec_tool("calendar_delete", {"event_id": event_id})
            else:
                result = _exec_tool("calendar_list", {"period": "week"})
            self.send_message(chat_id, result)

        elif cmd in ("/mail", "/email"):
            parts = text.split(maxsplit=4)
            sub = parts[1] if len(parts) > 1 else "inbox"
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            if sub == "inbox":
                result = _exec_tool("email_inbox", {})
            elif sub == "read":
                msg_id = parts[2] if len(parts) > 2 else ""
                if not msg_id:
                    self.send_message(chat_id, "❌ Usage: /mail read <message_id>")
                    return
                result = _exec_tool("email_read", {"message_id": msg_id})
            elif sub == "send":
                # /mail send to@email.com "제목" "본문"
                if len(parts) < 4:
                    self.send_message(chat_id, '❌ Usage: /mail send to@email.com "제목" "본문"')
                    return
                to_addr = parts[2]
                rest = text.split(to_addr, 1)[1].strip() if to_addr in text else ""
                # Parse quoted subject and body
                import shlex

                try:
                    parsed = shlex.split(rest)
                except ValueError:
                    parsed = rest.split(maxsplit=1)
                subject = parsed[0] if parsed else "No subject"
                body = parsed[1] if len(parsed) > 1 else ""
                result = _exec_tool("email_send", {"to": to_addr, "subject": subject, "body": body})
            elif sub == "search":
                query = " ".join(parts[2:]) if len(parts) > 2 else ""
                if not query:
                    self.send_message(chat_id, "❌ Usage: /mail search <query>")
                    return
                result = _exec_tool("email_search", {"query": query})
            else:
                result = _exec_tool("email_inbox", {})
            self.send_message(chat_id, result)

        elif cmd == "/briefing":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            sections = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else None
            args = {"sections": sections} if sections else {}
            result = _exec_tool("briefing", args)
            self.send_message(chat_id, result)

        elif cmd == "/note":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "search":
                query = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("note", {"action": "search", "query": query})
                    if query
                    else "❌ Usage: /note search <keyword>"
                )
            elif sub == "list":
                result = _exec_tool("note", {"action": "list"})
            elif sub == "tag":
                # /note tag work "content..."
                rest = text.split(maxsplit=3)
                tag = rest[2] if len(rest) > 2 else ""
                content = rest[3] if len(rest) > 3 else ""
                result = (
                    _exec_tool("note", {"action": "save", "content": content, "tags": tag})
                    if content
                    else "❌ Usage: /note tag <tag> <content>"
                )
            elif sub == "delete":
                nid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("note", {"action": "delete", "note_id": nid}) if nid else "❌ Usage: /note delete <id>"
                )
            else:
                # /note <content> → save directly
                content = text[len("/note") :].strip()
                result = (
                    _exec_tool("note", {"action": "save", "content": content})
                    if content
                    else "❌ Usage: /note <content> or /note search/list/tag/delete"
                )
            self.send_message(chat_id, result)

        elif cmd == "/expense":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=3)
            sub = parts[1] if len(parts) > 1 else "today"
            if sub == "add":
                # /expense add 점심 12000 식비
                rest = text.split(maxsplit=1)[1][4:].strip() if len(text) > 12 else ""
                eparts = rest.split()
                if len(eparts) >= 2:
                    desc = eparts[0]
                    amount = eparts[1]
                    cat = eparts[2] if len(eparts) > 2 else ""
                    result = _exec_tool(
                        "expense", {"action": "add", "description": desc, "amount": amount, "category": cat}
                    )
                else:
                    result = "❌ Usage: /expense add <description> <amount> [category]"
            elif sub == "today":
                result = _exec_tool("expense", {"action": "today"})
            elif sub == "month":
                month = parts[2] if len(parts) > 2 else ""
                args = {"action": "month"}
                if month:
                    args["month"] = month
                result = _exec_tool("expense", args)
            elif sub == "delete":
                eid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("expense", {"action": "delete", "expense_id": eid})
                    if eid
                    else "❌ Usage: /expense delete <id>"
                )
            else:
                result = _exec_tool("expense", {"action": "today"})
            self.send_message(chat_id, result)

        elif cmd == "/save":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            url = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if url:
                result = _exec_tool("save_link", {"action": "save", "url": url})
            else:
                result = "❌ Usage: /save <url>"
            self.send_message(chat_id, result)

        elif cmd == "/saved":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else "list"
            if sub == "list":
                result = _exec_tool("save_link", {"action": "list"})
            elif sub == "search":
                query = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("save_link", {"action": "search", "query": query})
                    if query
                    else "❌ Usage: /saved search <keyword>"
                )
            elif sub == "delete":
                lid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("save_link", {"action": "delete", "link_id": lid})
                    if lid
                    else "❌ Usage: /saved delete <id>"
                )
            else:
                result = _exec_tool("save_link", {"action": "list"})
            self.send_message(chat_id, result)

        elif cmd == "/pomodoro":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else "status"
            if sub == "start":
                duration = parts[2] if len(parts) > 2 else "25"
                result = _exec_tool("pomodoro", {"action": "start", "duration": duration})
            elif sub == "break":
                duration = parts[2] if len(parts) > 2 else "5"
                result = _exec_tool("pomodoro", {"action": "break", "duration": duration})
            elif sub == "stop":
                result = _exec_tool("pomodoro", {"action": "stop"})
            else:
                result = _exec_tool("pomodoro", {"action": "status"})
            self.send_message(chat_id, result)

        elif cmd == "/routine":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else "list"
            result = _exec_tool("routine", {"action": sub})
            self.send_message(chat_id, result)

        elif cmd == "/remind":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else "list"
            if sub == "list":
                result = _exec_tool("reminder", {"action": "list"})
            elif sub == "delete":
                rid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("reminder", {"action": "delete", "reminder_id": rid})
                    if rid
                    else "❌ Usage: /remind delete <id>"
                )
            else:
                result = _exec_tool("reminder", {"action": "list"})
            self.send_message(chat_id, result)

        elif cmd == "/tr":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            if len(parts) >= 3:
                target_lang = parts[1]
                tr_text = parts[2]
                result = _exec_tool("translate", {"text": tr_text, "target": target_lang})
            else:
                result = "❌ Usage: /tr <lang> <text>\nExample: /tr en 안녕하세요"
            self.send_message(chat_id, result)

        elif cmd == "/export":
            self.send_typing(chat_id)
            try:
                from salmalm.utils.migration import export_agent, export_filename

                parts = text.split()
                include_vault = "--vault" in parts
                zip_bytes = export_agent(include_vault=include_vault)
                fname = export_filename()
                # Send as document
                self._send_document(chat_id, zip_bytes, fname, caption=f"📦 Agent Export ({len(zip_bytes) // 1024}KB)")
            except Exception as e:
                self.send_message(chat_id, f"❌ Export failed: {e}")

        elif cmd == "/import":
            self.send_message(
                chat_id,
                "📦 에이전트 가져오기: ZIP 파일을 이 채팅에 보내주세요.\n"
                "Agent import: Send a ZIP file to this chat.\n"
                "(salmalm-agent-export-*.zip)",
            )

        elif cmd == "/sync":
            parts = text.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else "export"
            if sub == "export":
                from salmalm.utils.migration import quick_sync_export

                data = quick_sync_export()
                sync_json = json.dumps(data, ensure_ascii=False, indent=2)
                self.send_message(chat_id, f"📋 Quick Sync Export\n```json\n{sync_json[:3500]}\n```")
            elif sub.startswith("import"):
                json_str = sub[len("import") :].strip()
                if not json_str:
                    self.send_message(chat_id, "❌ Usage: /sync import <json>")
                    return
                try:
                    data = json.loads(json_str)
                    from salmalm.utils.migration import quick_sync_import

                    quick_sync_import(data)
                    self.send_message(chat_id, "✅ Quick sync imported / 빠른 동기화 완료")
                except json.JSONDecodeError:
                    self.send_message(chat_id, "❌ Invalid JSON")
                except Exception as e:
                    self.send_message(chat_id, f"❌ {e}")
            else:
                self.send_message(chat_id, "Usage: /sync export | /sync import <json>")

        else:
            # Route unknown /commands through engine (handles /model auto/opus/sonnet/haiku etc.)
            self.send_typing(chat_id)
            session_id = f"telegram_{chat_id}"
            from salmalm.core.engine import process_message

            response = await process_message(session_id, text)
            self.send_message(chat_id, response)

