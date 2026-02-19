"""Backward-compatibility shim — re-exports from decomposed modules."""
# fmt: off
from salmalm.features.abort import AbortController, abort_controller
from salmalm.features.usage import UsageTracker, usage_tracker
from salmalm.features.fork import ConversationFork, conversation_fork
from salmalm.features.provider_health import ProviderHealthCheck, provider_health
from salmalm.features.model_detect import ModelDetector, model_detector
from salmalm.features.file_upload import (ALLOWED_UPLOAD_EXTENSIONS, validate_upload,
                                           extract_pdf_text, process_uploaded_file)
from salmalm.features.session_groups import SessionGroupManager, session_groups
from salmalm.features.bookmarks import BookmarkManager, bookmark_manager
from salmalm.features.prompt_vars import substitute_prompt_variables
from salmalm.features.compare import compare_models
from salmalm.features.smart_paste import detect_paste_type
from salmalm.features.summary_card import get_summary_card
# fmt: on

__all__ = [
    'AbortController', 'abort_controller',
    'UsageTracker', 'usage_tracker',
    'ConversationFork', 'conversation_fork',
    'ProviderHealthCheck', 'provider_health',
    'ModelDetector', 'model_detector',
    'ALLOWED_UPLOAD_EXTENSIONS', 'validate_upload', 'extract_pdf_text', 'process_uploaded_file',
    'SessionGroupManager', 'session_groups',
    'BookmarkManager', 'bookmark_manager',
    'substitute_prompt_variables',
    'compare_models',
    'detect_paste_type',
    'get_summary_card',
]
