#!/usr/bin/env python3
"""Split app.js into numbered modules based on section comments."""
import os, re

APP_JS = os.path.join(os.path.dirname(__file__), '..', 'salmalm', 'static', 'app.js')
JS_DIR = os.path.join(os.path.dirname(__file__), '..', 'salmalm', 'static', 'js')
I18N_JS = os.path.join(os.path.dirname(__file__), '..', 'salmalm', 'static', 'i18n.js')
FEATURES_JS = os.path.join(os.path.dirname(__file__), '..', 'salmalm', 'static', 'features-data.js')

# Module boundaries: (line_content_match, output_filename)
# Each module starts at the line matching the pattern
BOUNDARIES = [
    # line 1: IIFE open — skip
    (r'Global error handlers', '00-core.js'),           # DOM refs + state + error handler
    (r'Session Management', '05-sessions.js'),           # loadSessionList, switchSession, etc
    (r'Restore chat history', '10-restore.js'),          # _pendingRestore
    (r'Export chat', '12-export.js'),                    # exportChat
    (r'New chat', '14-newchat.js'),                      # newChat alias
    (r'Theme', '16-theme.js'),                           # theme + color
    (r'Sidebar toggle', '18-sidebar.js'),                # toggleSidebar
    (r'Quick command from sidebar', '19-quickcmd.js'),   # quickCmd
    (r'Helpers', '20-helpers.js'),                       # renderMd, addMsg, etc
    (r'File handling', '25-files.js'),                   # setFile, clearFile
    (r'Ctrl\+V', '26-paste.js'),                        # paste handler
    (r'Drag & drop', '27-dragdrop.js'),                  # drag & drop
    (r'WebSocket Connection Manager', '30-websocket.js'),
    (r'Send via WebSocket with SSE', '35-chat-send.js'),
    (r'--- Send ---', '36-dosend.js'),                   # doSend
    (r'Key handler', '37-keyhandler.js'),                # key handler + input resize
    (r'--- i18n ---', '40-i18n.js'),                     # _i18n, t(), applyLang, tools
    (r'--- Settings ---', '45-settings.js'),             # view management, showSettings
    (r'Settings Tabs', '50-tabs.js'),                    # tab click handlers
    (r'Model Router Tab', '55-model-router.js'),         # prices, _loadModelRouter
    (r'Features Guide', '60-features.js'),               # FEATURE_CATEGORIES, renderFeatures
    (r'Users Panel', '65-users.js'),                     # multi-tenant
    (r'var _dashMode=', '70-dashboard.js'),                # showDashboard
    (r'Drag highlight', '75-ui.js'),                     # drag highlight + scroll + syntax
    (r'Keyboard shortcuts', '80-shortcuts.js'),          # shortcuts + filter + search modals
    (r'Welcome \(only if', '82-welcome.js'),             # welcome + restore model
    (r'Notification polling', '84-polling.js'),          # notification polling
    (r'Export menu toggle', '85-export-menu.js'),        # export menu + import
    (r'Command Palette', '90-cmdpalette.js'),            # command palette
    (r'PWA Install', '92-pwa.js'),                       # PWA + applyLang + toast
    (r'CSP-safe event delegation', '95-events.js'),      # big event handler
    (r'STT.*Voice Input', '97-voice.js'),                  # thinking + mic + STT
    (r'/\* --- Double-click to rename session title', '98-rename.js'),  # rename + auto-update
    (r'Agent Migration', '99-migration.js'),             # migration + SW + panels
]

def split():
    with open(APP_JS, 'r') as f:
        lines = f.readlines()
    
    # Strip IIFE wrapper
    # First line: (function(){
    # Last line: })();
    if lines[0].strip().startswith('(function()'):
        lines[0] = ''  # Remove IIFE open
    # Find and remove closing
    for i in range(len(lines)-1, -1, -1):
        if lines[i].strip() == '})();':
            lines[i] = ''
            break
    
    # Find boundary line numbers
    boundary_lines = []
    for pattern, filename in BOUNDARIES:
        if pattern is None:
            boundary_lines.append(None)
            continue
        found = False
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                boundary_lines.append(i)
                found = True
                break
        if not found:
            print(f"⚠️ Pattern not found: {pattern} → {filename}")
            boundary_lines.append(None)
    
    # Build modules
    os.makedirs(JS_DIR, exist_ok=True)
    
    # First module: from line 0 to first boundary
    first_boundary = next(b for b in boundary_lines if b is not None)
    
    # Collect all modules with their start lines
    modules = []
    # Core: everything before the first section comment
    modules.append(('00-core.js', 0, first_boundary))
    
    for idx, (pattern, filename) in enumerate(BOUNDARIES):
        start = boundary_lines[idx]
        if start is None:
            continue
        
        # Find end: next boundary that exists
        end = len(lines)
        for j in range(idx + 1, len(BOUNDARIES)):
            if boundary_lines[j] is not None:
                end = boundary_lines[j]
                break
        
        modules.append((filename, start, end))
    
    # Deduplicate (00-core.js might overlap with first boundary)
    seen = set()
    unique_modules = []
    for name, start, end in modules:
        if name not in seen:
            seen.add(name)
            unique_modules.append((name, start, end))
    
    total_written = 0
    for name, start, end in unique_modules:
        content = ''.join(lines[start:end])
        # Strip leading/trailing blank lines
        content = content.strip('\n') + '\n'
        
        filepath = os.path.join(JS_DIR, name)
        with open(filepath, 'w') as f:
            f.write(content)
        
        n = content.count('\n')
        total_written += n
        print(f"  {name}: {n} lines (L{start+1}-L{end})")
    
    print(f"\n✅ Split into {len(unique_modules)} modules, {total_written} total lines")
    print(f"   Original (minus IIFE): {sum(1 for l in lines if l.strip())} non-empty lines")

if __name__ == '__main__':
    split()
