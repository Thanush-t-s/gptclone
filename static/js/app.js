/* =========================================================================
   AI Chatbot — front-end controller
   - Theme handling (no-flash, persisted, respects system preference)
   - Safe Markdown rendering (marked + highlight.js + DOMPurify)
   - Chat UI: sidebar, history, composer, loading states
   All backend routes/APIs are used exactly as provided; nothing here changes
   the server contract.
   ========================================================================= */

/* ------------------------------- State -------------------------------- */
let currentConversationId = null;
let username = 'User';

/* ------------------------------- Theme -------------------------------- */
function getPreferredTheme() {
    try {
        var saved = localStorage.getItem('theme');
        if (saved) return saved;
    } catch (e) { /* ignore */ }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme) {
    var root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.style.colorScheme = theme;
    // Sync any theme icons on the page
    document.querySelectorAll('[data-theme-icon]').forEach(function (icon) {
        var dark = theme === 'dark';
        icon.classList.toggle('fa-moon', !dark);
        icon.classList.toggle('fa-sun', dark);
    });
    try { localStorage.setItem('theme', theme); } catch (e) { /* ignore */ }
}

function initTheme() {
    applyTheme(getPreferredTheme());
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var next = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
            applyTheme(next);
        });
    });
}

/* ------------------------------- Toasts ------------------------------- */
function showToast(message, type) {
    type = type || 'error';
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.setAttribute('role', 'status');
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function () {
        toast.style.transition = 'opacity 0.3s ease';
        toast.style.opacity = '0';
        setTimeout(function () { toast.remove(); }, 300);
    }, 3800);
}

/* ---------------------------- Text helpers ---------------------------- */
function escapeHtml(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text == null ? '' : String(text)));
    return div.innerHTML;
}

/* --------------------------- Markdown render -------------------------- */
var mdReady = false;
function initMarkdown() {
    if (window.marked) {
        marked.setOptions({ gfm: true, breaks: true });
        mdReady = true;
    }
}

// Add a language label + copy button to a highlighted <pre><code> block.
// No click listener is attached here on purpose: these nodes are produced in
// a detached div and then re-inserted with body.innerHTML (which also goes
// through DOMPurify), and that round-trip discards element references and
// their listeners. A single delegated handler in initChat() does the copying.
function decorateCodeBlock(pre, code) {
    var lang = (code.getAttribute('class') || '').match(/language-([\w+-]+)/);
    lang = lang ? lang[1] : '';
    if (lang) {
        var label = document.createElement('span');
        label.className = 'code-lang';
        label.textContent = lang;
        pre.appendChild(label);
    }
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.setAttribute('aria-label', 'Copy code');
    pre.appendChild(btn);
}

// Convert Markdown to sanitized, syntax-highlighted HTML.
function renderMarkdown(text) {
    if (!text) return '';
    if (!mdReady || !window.marked) return escapeHtml(text).replace(/\n/g, '<br>');

    var html = marked.parse(String(text));
    var tmp = document.createElement('div');
    tmp.innerHTML = html;

    // Syntax highlight fenced code blocks
    if (window.hljs) {
        tmp.querySelectorAll('pre > code').forEach(function (block) {
            try { hljs.highlightElement(block); } catch (e) { /* leave as-is */ }
            decorateCodeBlock(block.parentNode, block);
        });
    }

    // Sanitize to prevent XSS, then return
    if (window.DOMPurify) {
        return DOMPurify.sanitize(tmp.innerHTML, { ADD_ATTR: ['target'] });
    }
    return tmp.innerHTML;
}

/* --------------------------- Clipboard helper ------------------------- */
function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* ignore */ }
    ta.remove();
}

function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
    }
    return Promise.resolve(fallbackCopy(text));
}

/* ======================================================================
   Chat controller
   ====================================================================== */
function initChat() {
    var stream = document.getElementById('chatStream');
    var scrollArea = document.getElementById('scrollArea');
    var form = document.getElementById('messageForm');
    var composer = form; // the single composer element is the form itself
    var input = document.getElementById('messageInput');
    var sendBtn = document.getElementById('sendBtn');
    var welcome = document.getElementById('welcome');
    var welcomeSlot = document.getElementById('welcomeComposerSlot');
    var dockSlot = document.getElementById('dockSlot');
    var titleEl = document.getElementById('chatTitle');
    var backdrop = document.getElementById('sidebarBackdrop');
    var sidebar = document.getElementById('sidebar');

    if (!stream || !form) return; // not the chat page

    initMarkdown();

    /* ------------------- Streaming / scroll tracking ------------------ */
    // True while the viewport is pinned near the bottom. Streaming only
    // auto-scrolls when this is set, so a user reading older output is not
    // yanked down as new text arrives (ChatGPT behaviour).
    var nearBottom = true;
    var isSending = false;
    scrollArea.addEventListener('scroll', function () {
        nearBottom = (scrollArea.scrollHeight - scrollArea.scrollTop -
                      scrollArea.clientHeight) < 80;
    }, { passive: true });

    /* ---------------------- Empty / active layout ---------------------- */
    function setChatState(state) {
        var isEmpty = state === 'empty';
        if (welcome) welcome.hidden = !isEmpty;
        if (isEmpty) {
            welcomeSlot.appendChild(composer);
        } else {
            dockSlot.appendChild(composer);
        }
    }
    setChatState('empty'); // fresh /chat load is always empty

    // Render the sidebar from the server-provided JSON. This function was
    // previously called but never defined, which threw a ReferenceError and
    // aborted initChat() before any handlers were bound.
    function renderConversationList() {
        var dataEl = document.getElementById('conversationsData');
        var listEl = document.getElementById('convList');
        var emptyEl = document.getElementById('convEmpty');
        if (!listEl) return;

        var items = [];
        if (dataEl) {
            try { items = JSON.parse(dataEl.textContent || '[]') || []; }
            catch (e) { items = []; }
        }

        listEl.innerHTML = '';
        if (!items.length) {
            if (emptyEl) emptyEl.style.display = '';
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';
        items.forEach(function (c) { listEl.appendChild(buildConvItem(c)); });
    }
    renderConversationList();

    /* ------------------------------ Sidebar ---------------------------- */
    var sidebarOpenOnMobile = false;
    function isMobile() { return window.matchMedia('(max-width: 767px)').matches; }

    function openMobileSidebar() {
        sidebar.classList.remove('-translate-x-full');
        backdrop.classList.add('open');
        sidebarOpenOnMobile = true;
    }
    function closeMobileSidebar() {
        if (isMobile()) sidebar.classList.add('-translate-x-full');
        backdrop.classList.remove('open');
        sidebarOpenOnMobile = false;
    }

    // Desktop collapse persists; mobile uses a drawer + backdrop.
    var toggleBtn = document.getElementById('sidebarToggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', function () {
            if (isMobile()) {
                sidebarOpenOnMobile ? closeMobileSidebar() : openMobileSidebar();
            } else {
                var collapsed = sidebar.classList.toggle('md:translate-x-full');
                try { localStorage.setItem('sidebar_collapsed', collapsed ? '1' : '0'); } catch (e) {}
            }
        });
    }
    // The header hamburger (visible on small screens) opens the drawer.
    var toggleMobileBtn = document.getElementById('sidebarToggleMobile');
    if (toggleMobileBtn) {
        toggleMobileBtn.addEventListener('click', function () {
            if (sidebarOpenOnMobile) closeMobileSidebar(); else openMobileSidebar();
        });
    }
    if (backdrop) backdrop.addEventListener('click', closeMobileSidebar);

    // Restore desktop collapse preference
    try {
        if (!isMobile() && localStorage.getItem('sidebar_collapsed') === '1') {
            sidebar.classList.add('md:translate-x-full');
        }
    } catch (e) {}

    // On load, ensure the drawer is hidden on small screens
    if (isMobile()) sidebar.classList.add('-translate-x-full');

    /* --------------------------- New chat ------------------------------ */
    var newChatBtn = document.getElementById('newChatBtn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            // Switching away mid-stream would orphan the in-flight reply.
            if (isSending) { showToast('Please wait for the current reply to finish…'); return; }
            resetToEmpty();
            closeMobileSidebar();
        });
    }

    function resetToEmpty() {
        currentConversationId = null;
        stream.innerHTML = '';
        setChatState('empty');
        if (titleEl) titleEl.textContent = 'New Chat';
        setActiveConv(null);
        input.focus();
        scrollArea.scrollTop = 0;
    }

    /* --------------------- Conversation list / history ----------------- */
    function setActiveConv(id) {
        document.querySelectorAll('.conv-item').forEach(function (el) {
            var active = id != null && el.getAttribute('data-conv-id') === String(id);
            el.classList.toggle('bg-brand-50', active);
            el.classList.toggle('dark:bg-white/5', active);
            el.classList.toggle('text-brand-700', active);
            el.classList.toggle('dark:text-brand-300', active);
        });
    }

    function relTime(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        if (isNaN(d)) return '';
        var diff = (Date.now() - d.getTime()) / 1000;
        if (diff < 60) return 'now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h';
        if (diff < 604800) return Math.floor(diff / 86400) + 'd';
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }

    function buildConvItem(c) {
        var item = document.createElement('div');
        item.className = 'conv-item group relative flex items-center gap-3 px-2.5 py-2 rounded-lg cursor-pointer text-[0.9rem] text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors';
        item.setAttribute('data-conv-id', c.id);
        item.setAttribute('tabindex', '0');
        item.setAttribute('role', 'button');
        item.setAttribute('aria-label', 'Open conversation: ' + (c.title || 'Untitled'));

        var icon = document.createElement('i');
        icon.className = 'fas fa-message text-[11px] text-gray-400 shrink-0';

        var body = document.createElement('div');
        body.className = 'flex-1 min-w-0';
        var t = document.createElement('div');
        t.className = 'truncate font-medium';
        t.textContent = c.title || 'New Conversation';
        body.appendChild(t);
        if (c.last_message) {
            var p = document.createElement('div');
            p.className = 'truncate text-[0.72rem] text-gray-400 dark:text-gray-500 mt-0.5';
            p.textContent = c.last_message;
            body.appendChild(p);
        }

        var time = document.createElement('span');
        time.className = 'text-[0.68rem] text-gray-400 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity';
        time.textContent = relTime(c.updated_at);

        var menuBtn = document.createElement('button');
        menuBtn.type = 'button';
        menuBtn.className = 'conv-menu-btn shrink-0 w-6 h-6 grid place-items-center rounded hover:bg-gray-200 dark:hover:bg-white/10 text-gray-500';
        menuBtn.setAttribute('aria-label', 'Conversation options');
        menuBtn.innerHTML = '<i class="fas fa-ellipsis-vertical text-[11px]"></i>';
        menuBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            openConvMenu(item, c, menuBtn);
        });

        item.appendChild(icon);
        item.appendChild(body);
        item.appendChild(time);
        item.appendChild(menuBtn);

        item.addEventListener('click', function () { openConversation(c.id); });
        item.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openConversation(c.id); }
        });
        return item;
    }

    function openConvMenu(item, c, anchor) {
        closeConvMenus();
        var menu = document.createElement('div');
        menu.className = 'conv-menu animate-pop';
        menu.setAttribute('role', 'menu');

        var rename = document.createElement('button');
        rename.type = 'button';
        rename.setAttribute('role', 'menuitem');
        rename.innerHTML = '<i class="fas fa-pen w-3"></i> Rename';
        rename.addEventListener('click', function (e) {
            e.stopPropagation();
            closeConvMenus();
            renameConversation(c, item);
        });

        var del = document.createElement('button');
        del.type = 'button';
        del.className = 'danger';
        del.setAttribute('role', 'menuitem');
        del.innerHTML = '<i class="fas fa-trash w-3"></i> Delete';
        del.addEventListener('click', function (e) {
            e.stopPropagation();
            closeConvMenus();
            deleteConversation(c, item);
        });

        menu.appendChild(rename);
        menu.appendChild(del);
        item.appendChild(menu);
    }
    function closeConvMenus() {
        document.querySelectorAll('.conv-menu').forEach(function (m) { m.remove(); });
    }
    document.addEventListener('click', closeConvMenus);

    function renameConversation(c, item) {
        var next = window.prompt('Rename conversation', c.title || 'New Conversation');
        if (next == null) return;
        next = next.trim();
        if (!next) return;
        fetch('/api/rename-conversation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: c.id, title: next })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (data.success) {
                var t = item.querySelector('.truncate');
                if (t) t.textContent = next;
                if (String(currentConversationId) === String(c.id) && titleEl) titleEl.textContent = next;
                showToast('Renamed', 'success');
            } else {
                showToast(data.error || 'Rename failed');
            }
        }).catch(function () { showToast('Rename failed'); });
    }

    function deleteConversation(c, item) {
        if (!window.confirm('Delete this conversation? This cannot be undone.')) return;
        fetch('/api/delete-conversation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: c.id })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (data.success) {
                item.remove();
                if (String(currentConversationId) === String(c.id)) resetToEmpty();
                showToast('Conversation deleted', 'success');
            } else {
                showToast(data.error || 'Delete failed');
            }
        }).catch(function () { showToast('Delete failed'); });
    }

    /* -------------------------- Sidebar search ------------------------- */
    var searchInput = document.getElementById('convSearch');
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            var q = searchInput.value.trim().toLowerCase();
            document.querySelectorAll('.conv-item').forEach(function (el) {
                var title = (el.getAttribute('aria-label') || '').toLowerCase();
                el.style.display = (!q || title.indexOf(q) !== -1) ? '' : 'none';
            });
        });
    }

    /* --------------------------- Open conversation --------------------- */
    function openConversation(id) {
        // Switching conversations mid-stream would orphan the in-flight reply.
        if (isSending) { showToast('Please wait for the current reply to finish…'); return; }
        fetch('/api/conversation/' + id)
            .then(function (r) { if (!r.ok) throw new Error('not found'); return r.json(); })
            .then(function (data) {
                currentConversationId = data.conversation.id;
                stream.innerHTML = '';
                (data.messages || []).forEach(function (m) {
                    appendMessage(m.role, m.content, m.created_at, true);
                });
                if (titleEl) titleEl.textContent = data.conversation.title || 'New Chat';
                setChatState('active');
                setActiveConv(id);
                closeMobileSidebar();
                scrollToBottom(true);
            })
            .catch(function () { showToast('Could not load conversation'); });
    }

    /* ---------------------------- Message UI --------------------------- */
    function avatar() {
        var a = document.createElement('div');
        a.className = 'shrink-0 w-8 h-8 rounded-lg grid place-items-center bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm overflow-hidden p-1.5';
        a.innerHTML = '<img src="/static/images/logo-white.svg" alt="Aura Logo" class="w-full h-full object-contain pointer-events-none drop-shadow-sm">';
        return a;
    }

    function timeLabel(iso) {
        var d = iso ? new Date(iso) : new Date();
        if (isNaN(d)) d = new Date();
        return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }

    // Assistant message shell: avatar + prose body + action row. Shared by
    // completed history messages and by the in-flight streaming bubble, so
    // both render (and behave) identically.
    //   streaming=true -> actions stay hidden and the buffer is re-rendered
    //   incrementally until the reply is complete.
    function createAssistantShell(iso, streaming) {
        var wrap = document.createElement('div');
        wrap.className = 'msg flex gap-3 animate-fade-up';
        wrap.setAttribute('data-role', 'assistant');
        if (streaming) wrap.setAttribute('data-streaming', 'true');
        wrap.appendChild(avatar());

        var col = document.createElement('div');
        col.className = 'min-w-0 flex-1';

        var body = document.createElement('div');
        body.className = 'prose dark:prose-invert max-w-none text-gray-900 dark:text-gray-100';

        var actions = document.createElement('div');
        actions.className = 'msg-actions flex items-center gap-1 mt-1 -ml-1 opacity-0 hover:opacity-100 focus-within:opacity-100 transition-opacity';
        actions.hidden = !!streaming; // no Copy/Regenerate until it's finished
        actions.innerHTML =
            '<button type="button" class="msg-copy w-7 h-7 grid place-items-center rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 hover:text-gray-600 dark:hover:text-gray-200" aria-label="Copy response" title="Copy"><i class="far fa-copy text-[13px]"></i></button>' +
            '<button type="button" class="msg-regen w-7 h-7 grid place-items-center rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 hover:text-gray-600 dark:hover:text-gray-200" aria-label="Regenerate response" title="Regenerate"><i class="fas fa-rotate-right text-[13px]"></i></button>' +
            '<span class="msg-time text-[0.68rem] text-gray-400 ml-1"></span>';
        var timeEl = actions.querySelector('.msg-time');
        if (timeEl) timeEl.textContent = timeLabel(iso);

        col.appendChild(body);
        col.appendChild(actions);
        wrap.appendChild(col);

        return {
            wrap: wrap, body: body, actions: actions,
            buffer: '', timer: null, lastRender: 0
        };
    }

    // Enable the action row once an answer is final. getContent is a function
    // so a streaming bubble copies its accumulated buffer, not a stale value.
    function finalizeShell(shell, getContent) {
        shell.actions.hidden = false;
        var copyBtn = shell.actions.querySelector('.msg-copy');
        var regenBtn = shell.actions.querySelector('.msg-regen');
        if (copyBtn) {
            copyBtn.onclick = function () {
                copyText(getContent()).then(function () {
                    showToast('Copied to clipboard', 'success');
                }).catch(function () { showToast('Copy failed'); });
            };
        }
        if (regenBtn) regenBtn.onclick = function () { regenerate(); };
    }

    // Build a message element. For assistant messages, render Markdown.
    function buildMessage(role, content, iso) {
        if (role === 'user') {
            var wrap = document.createElement('div');
            wrap.className = 'msg animate-fade-up flex justify-end';
            wrap.setAttribute('data-role', role);
            var bubble = document.createElement('div');
            bubble.className = 'max-w-[85%] md:max-w-[75%] rounded-2xl rounded-br-md bg-brand-600 text-white px-4 py-2.5 shadow-sm whitespace-pre-wrap break-words';
            bubble.textContent = content; // plain text (escaped by definition)
            wrap.appendChild(bubble);
            return wrap;
        }

        var shell = createAssistantShell(iso, false);
        shell.body.innerHTML = renderMarkdown(content);
        finalizeShell(shell, function () { return content; });
        return shell.wrap;
    }

    function appendMessage(role, content, iso, scrollTo) {
        var el = buildMessage(role, content, iso);
        stream.appendChild(el);
        if (scrollTo) scrollToBottom();
        return el;
    }

    // Show a temporary "thinking" indicator while waiting for the model.
    function showThinking() {
        var wrap = document.createElement('div');
        wrap.className = 'msg flex gap-3 animate-fade-up';
        wrap.id = 'thinkingMsg';
        wrap.setAttribute('aria-hidden', 'true');
        wrap.appendChild(avatar());
        var dots = document.createElement('div');
        dots.className = 'typing-dots text-gray-400 self-center';
        dots.innerHTML = '<span></span><span></span><span></span>';
        wrap.appendChild(dots);
        stream.appendChild(wrap);
        scrollToBottom();
        return wrap;
    }
    function hideThinking() {
        var el = document.getElementById('thinkingMsg');
        if (el) el.remove();
    }

    /* --------------------------- Sending messages ---------------------- */
    var lastSent = { message: null, conversationId: null };

    function nowMs() {
        return (window.performance && performance.now) ? performance.now() : Date.now();
    }

    /* --- NDJSON stream transport (/api/send-message-stream) ----------- */

    // Apply one server event to the stream state.
    function parseStreamLine(line, state, onDelta) {
        line = (line || '').trim();
        if (!line) return;
        var evt;
        try { evt = JSON.parse(line); } catch (e) { return; } // ignore junk lines
        if (evt.type === 'delta' && typeof evt.text === 'string') {
            if (onDelta) onDelta(evt.text);
        } else if (evt.type === 'done') {
            state.result = evt;
        } else if (evt.type === 'error') {
            if (evt.response) {
                // The text arrived but persisting it failed — keep the answer.
                state.result = {
                    response: evt.response,
                    conversation_id: evt.conversation_id,
                    save_error: evt.error
                };
            } else {
                state.error = new Error(evt.error || 'Stream failed');
            }
        }
    }

    function finishStream(state) {
        if (state.error) throw state.error;
        if (!state.result) throw new Error('Stream ended unexpectedly');
        return state.result;
    }

    // Read the NDJSON body line by line, invoking onDelta per text chunk.
    function readNdjsonStream(body, onDelta) {
        var reader = body.getReader();
        var decoder = new TextDecoder('utf-8');
        var state = { result: null, error: null };
        var buffered = '';

        function pump() {
            return reader.read().then(function (step) {
                if (step.done) {
                    parseStreamLine(buffered, state, onDelta);
                    return finishStream(state);
                }
                buffered += decoder.decode(step.value, { stream: true });
                var idx;
                while ((idx = buffered.indexOf('\n')) !== -1) {
                    parseStreamLine(buffered.substring(0, idx), state, onDelta);
                    buffered = buffered.substring(idx + 1);
                }
                return pump();
            });
        }
        return pump();
    }

    // Fallback for browsers without ReadableStream: parse the whole payload.
    function consumeNdjsonText(text, onDelta) {
        var state = { result: null, error: null };
        (text || '').split('\n').forEach(function (line) {
            parseStreamLine(line, state, onDelta);
        });
        return finishStream(state);
    }

    // Ask the model for a reply. Streams from /api/send-message-stream so the
    // Markdown renders incrementally, and falls back to the unchanged
    // /api/send-message endpoint ONLY when the streaming route never ran
    // (missing route / network failure before the request was processed) —
    // falling back after the handler ran would save the user message twice.
    // Resolves to { response, conversation_id, message_count, save_error? }.
    function requestAssistant(message, conversationId, regenerate, onDelta) {
        var payload = JSON.stringify({
            message: message,
            conversation_id: conversationId,
            regenerate: !!regenerate
        });

        function jsonFallback() {
            return fetch('/api/send-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload
            }).then(function (r) {
                return r.json().then(function (data) {
                    if (!r.ok || !data.success || !data.response) {
                        throw new Error(data.error || 'Failed to get a response');
                    }
                    return data;
                });
            });
        }

        var reachedServer = false;

        return fetch('/api/send-message-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/x-ndjson' },
            body: payload
        }).then(function (res) {
            reachedServer = true;
            var ct = (res.headers.get('content-type') || '').toLowerCase();

            if (ct.indexOf('ndjson') !== -1) {
                if (res.body) return readNdjsonStream(res.body, onDelta);
                return res.text().then(function (t) { return consumeNdjsonText(t, onDelta); });
            }
            if (ct.indexOf('json') !== -1) {
                // JSON error from the view itself (401/400/conversation gone).
                return res.json().then(function (data) {
                    if (data && data.success && data.response) return data;
                    throw new Error((data && data.error) || 'Failed to get a response');
                }, function () {
                    throw new Error('Failed to get a response');
                });
            }
            if (res.status === 404) { // route not registered — nothing ran
                reachedServer = false;
                return jsonFallback();
            }
            throw new Error('Unexpected server response (' + res.status + ')');
        }).catch(function (err) {
            if (!reachedServer && err instanceof TypeError) return jsonFallback();
            throw err;
        });
    }

    /* --- Incremental Markdown rendering while streaming ---------------- */

    // Re-render the accumulated buffer, throttled so long replies do not
    // re-parse + re-highlight more than ~15x per second. Whitespace and
    // partial fences are safe: each render starts from the raw Markdown.
    function scheduleStreamRender(shell) {
        if (shell.timer) return;
        var wait = Math.max(0, 66 - (nowMs() - shell.lastRender));
        shell.timer = setTimeout(function () {
            shell.timer = null;
            shell.lastRender = nowMs();
            shell.body.innerHTML = renderMarkdown(shell.buffer);
            if (nearBottom) scrollArea.scrollTop = scrollArea.scrollHeight;
        }, wait);
    }

    // Complete a streaming bubble: one final render, actions revealed, and —
    // if the reply stopped early — a visible inline error under the text so
    // an incomplete answer is never presented as a complete one.
    function finalizeBubble(shell, text, errorMsg) {
        if (shell.timer) { clearTimeout(shell.timer); shell.timer = null; }
        shell.buffer = text || shell.buffer;
        shell.body.innerHTML = renderMarkdown(shell.buffer);
        if (errorMsg) {
            var note = document.createElement('div');
            note.className = 'stream-error';
            note.textContent = errorMsg;
            shell.body.appendChild(note);
        }
        shell.wrap.removeAttribute('data-streaming');
        finalizeShell(shell, function () { return shell.buffer; });
        nearBottom = true;
        scrollToBottom();
    }

    // Shared exchange: thinking indicator -> streamed answer -> finalize.
    function runExchange(message, conversationId, regenerate) {
        if (isSending) { showToast('Please wait for the current reply to finish…'); return; }

        var isNewConversation = conversationId == null;
        var shell = null;
        isSending = true;
        setSending(true);
        showThinking();

        function ensureShell() {
            if (!shell) {
                hideThinking();
                shell = createAssistantShell(null, true);
                stream.appendChild(shell.wrap);
            }
            return shell;
        }

        requestAssistant(message, conversationId, regenerate, function (delta) {
            var s = ensureShell();
            s.buffer += delta;
            scheduleStreamRender(s);
        })
            .then(function (data) {
                var s = ensureShell();
                if (data.conversation_id) currentConversationId = data.conversation_id;
                finalizeBubble(s, data.response || s.buffer);
                if (data.save_error) {
                    showToast('Reply received but could not be saved: ' + data.save_error);
                }
                if (isNewConversation && data.conversation_id) autoTitle(data.conversation_id, message);
                else setActiveConv(currentConversationId);
            })
            .catch(function (err) {
                if (shell && shell.buffer) {
                    finalizeBubble(shell, shell.buffer,
                        'The response was interrupted: ' + (err.message || 'connection lost'));
                } else if (shell) {
                    shell.wrap.remove();
                }
                showToast(err.message || 'Network error — please try again');
            })
            .finally(function () {
                hideThinking();
                isSending = false;
                setSending(false);
                input.focus();
            });
    }

    function sendMessage(raw) {
        var message = (raw || '').trim();
        if (!message) return;
        if (isSending) { showToast('Please wait for the current reply to finish…'); return; }

        appendMessage('user', message);
        setChatState('active');
        nearBottom = true;
        scrollArea.scrollTop = scrollArea.scrollHeight;

        lastSent = { message: message, conversationId: currentConversationId };
        runExchange(message, currentConversationId, false);
    }

    function regenerate() {
        if (!lastSent.message) return;
        if (isSending) { showToast('Please wait for the current reply to finish…'); return; }

        // Remove the last assistant bubble, then re-ask. The backend replaces
        // that turn (regenerate=true) instead of appending a duplicate user
        // message to the stored history.
        var msgs = stream.querySelectorAll('[data-role="assistant"]');
        if (msgs.length) msgs[msgs.length - 1].remove();
        var id = lastSent.conversationId != null ? lastSent.conversationId : currentConversationId;
        currentConversationId = id;
        nearBottom = true;
        scrollArea.scrollTop = scrollArea.scrollHeight;
        runExchange(lastSent.message, id, true);
    }

    // Set the conversation title to a trimmed version of the first prompt,
    // using the existing /api/rename-conversation endpoint.
    function autoTitle(convId, firstMessage) {
        var title = firstMessage.length > 42 ? firstMessage.slice(0, 42).trim() + '…' : firstMessage;
        if (titleEl) titleEl.textContent = title;
        fetch('/api/rename-conversation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: convId, title: title })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (data.success) addConvToSidebar(convId, title, firstMessage);
            else setActiveConv(currentConversationId);
        }).catch(function () { setActiveConv(currentConversationId); });
    }

    var convList = document.getElementById('convList');
    var convEmpty = document.getElementById('convEmpty');
    function addConvToSidebar(id, title, preview) {
        if (!convList) return;
        if (convEmpty) convEmpty.style.display = 'none';
        var item = buildConvItem({
            id: id, title: title, last_message: preview,
            updated_at: new Date().toISOString()
        });
        convList.insertBefore(item, convList.firstChild);
        setActiveConv(id);
    }

    function setSending(sending) {
        input.disabled = sending;
        sendBtn.disabled = sending;
        sendBtn.classList.toggle('opacity-50', sending);
        sendBtn.classList.toggle('cursor-not-allowed', sending);
        sendBtn.innerHTML = sending
            ? '<i class="fas fa-spinner fa-spin"></i>'
            : '<i class="fas fa-arrow-up"></i>';
    }

    /* ------------------------------ Composer --------------------------- */
    function autoResize() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 200) + 'px';
    }
    input.addEventListener('input', autoResize);

    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit', { cancelable: true }));
        }
    });

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var value = input.value;
        if (!value.trim()) return;
        input.value = '';
        autoResize();
        sendMessage(value);
    });

    /* -------------------------- Suggested prompts ---------------------- */
    document.querySelectorAll('[data-prompt]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            sendMessage(btn.getAttribute('data-prompt'));
        });
    });

    /* ----------------------- Global event delegation ------------------- */
    // Keyboard: Escape closes the mobile drawer / menus
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { closeMobileSidebar(); closeConvMenus(); }
    });

    // Keep the drawer state sane across resizes
    window.addEventListener('resize', function () {
        if (!isMobile()) {
            sidebar.classList.remove('-translate-x-full');
            backdrop.classList.remove('open');
        } else if (!sidebarOpenOnMobile) {
            sidebar.classList.add('-translate-x-full');
        }
    });

    function scrollToBottom(instant) {
        nearBottom = true;
        requestAnimationFrame(function () {
            scrollArea.scrollTo({ top: scrollArea.scrollHeight, behavior: instant ? 'auto' : 'smooth' });
        });
    }

    // ONE delegated handler for code-block Copy buttons. Those buttons are
    // rebuilt on every Markdown render (constantly during streaming), so
    // per-element listeners would be thrown away by the innerHTML swap.
    stream.addEventListener('click', function (e) {
        var t = e.target;
        if (!t || !t.closest) return;
        var btn = t.closest('.copy-btn');
        if (!btn) return;
        var pre = btn.closest('pre');
        var code = pre ? pre.querySelector('code') : null;
        var text = code ? code.textContent : (pre ? pre.textContent : '');
        var mark = function () {
            btn.textContent = 'Copied!';
            setTimeout(function () {
                if (btn.isConnected) btn.textContent = 'Copy';
            }, 1600);
        };
        copyText(text).then(mark).catch(function () { showToast('Copy failed'); });
    });

    // Autofocus the composer on desktop
    if (!isMobile()) input.focus();
}

/* ------------------------------- Boot --------------------------------- */
document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    if (document.getElementById('messageForm')) initChat();
});
