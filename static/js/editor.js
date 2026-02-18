/* =============================================================================
   AgentForge - IDE Editor JavaScript
   Monaco editor, file tree, chat, and change management
   ============================================================================= */

// Editor State
const EditorState = {
    project: null,
    sessionId: null,
    editor: null,
    currentFile: null,
    openFiles: new Map(), // path -> { content, modified }
    activeTab: null,
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    initializeEditor();
});

// Initialize the editor
async function initializeEditor() {
    const { API, UI, Utils } = window.AgentForge;
    
    console.log('AgentForge: Starting editor initialization...');

    // Load project data
    const projectDataEl = document.getElementById('project-data');
    if (projectDataEl) {
        try {
            EditorState.project = JSON.parse(projectDataEl.textContent);
            EditorState.sessionId = EditorState.project.sessionId;
            console.log('AgentForge: Project loaded:', EditorState.project.name);
        } catch (e) {
            console.error('AgentForge: Failed to parse project data:', e);
            return;
        }
    } else {
        console.error('AgentForge: No project data element found');
        return;
    }

    // Load file tree first (doesn't depend on Monaco)
    await loadFileTree();
    console.log('AgentForge: File tree loaded');

    // Initialize Monaco
    try {
        await initMonaco();
        console.log('AgentForge: Monaco initialized');
    } catch (e) {
        console.error('AgentForge: Monaco failed to load:', e);
    }

    // Setup event listeners
    setupEventListeners();

    // Setup chat
    setupChat();
    
    console.log('AgentForge: Editor initialization complete');
}

// Initialize Monaco Editor
async function initMonaco() {
    return new Promise((resolve, reject) => {
        // Check if require is available (Monaco loader)
        if (typeof require === 'undefined') {
            reject(new Error('Monaco loader not available'));
            return;
        }
        
        require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' } });
        
        // Add error handler for require
        require.onError = (err) => {
            console.error('Monaco require error:', err);
            reject(err);
        };
        
        require(['vs/editor/editor.main'], () => {
            // Define dark theme
            monaco.editor.defineTheme('agentforge-dark', {
                base: 'vs-dark',
                inherit: true,
                rules: [
                    { token: 'comment', foreground: '6B7280' },
                    { token: 'keyword', foreground: 'A855F7' },
                    { token: 'string', foreground: '34D399' },
                    { token: 'number', foreground: 'F59E0B' },
                    { token: 'type', foreground: '22D3EE' },
                ],
                colors: {
                    'editor.background': '#0B0F19',
                    'editor.foreground': '#F9FAFB',
                    'editor.lineHighlightBackground': '#1F2937',
                    'editor.selectionBackground': '#6366F133',
                    'editorCursor.foreground': '#6366F1',
                    'editorLineNumber.foreground': '#6B7280',
                    'editorLineNumber.activeForeground': '#9CA3AF',
                },
            });

            // Create editor
            const container = document.getElementById('monaco-editor');
            EditorState.editor = monaco.editor.create(container, {
                theme: 'agentforge-dark',
                language: 'python',
                fontSize: 14,
                fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
                minimap: { enabled: true },
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 4,
                insertSpaces: true,
                wordWrap: 'off',
                lineNumbers: 'on',
                renderLineHighlight: 'line',
                cursorBlinking: 'smooth',
                cursorSmoothCaretAnimation: 'on',
                smoothScrolling: true,
                padding: { top: 16 },
            });

            // Track changes
            EditorState.editor.onDidChangeModelContent(() => {
                if (EditorState.currentFile) {
                    const file = EditorState.openFiles.get(EditorState.currentFile);
                    if (file) {
                        file.modified = true;
                        updateTabModified(EditorState.currentFile, true);
                    }
                }
            });

            // Keyboard shortcuts
            EditorState.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
                saveCurrentFile();
            });

            resolve();
        });
    });
}

// Load file tree
async function loadFileTree() {
    const { API, Utils } = window.AgentForge;
    const fileTree = document.getElementById('file-tree');

    try {
        const result = await API.get(`/api/projects/${EditorState.project.id}/files/tree/`);

        if (result.success) {
            // Convert tree object to array, handle empty case
            const treeItems = Array.isArray(result.tree) ? result.tree : Object.values(result.tree || {});
            
            if (treeItems.length === 0) {
                fileTree.innerHTML = `
                    <div class="empty-tree">
                        <div class="empty-tree-message">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="32" height="32">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                            </svg>
                            <p>No files yet</p>
                            <span>Start by chatting with the AI to create your project</span>
                        </div>
                    </div>
                `;
            } else {
                fileTree.innerHTML = renderFileTree(treeItems);
                setupFileTreeEvents();
            }
        } else {
            fileTree.innerHTML = '<div class="loading">Failed to load files</div>';
        }
    } catch (error) {
        console.error('Error loading file tree:', error);
        fileTree.innerHTML = '<div class="loading">Error loading files</div>';
    }
}

// Render file tree recursively
function renderFileTree(items, level = 0) {
    const { Utils } = window.AgentForge;
    
    return items.map(item => {
        if (item.is_dir) {
            return `
                <div class="tree-folder" data-path="${item.path}">
                    <div class="tree-item" style="padding-left: ${level * 16 + 8}px">
                        <span class="tree-toggle">
                            <svg viewBox="0 0 20 20" fill="currentColor" width="12" height="12">
                                <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"/>
                            </svg>
                        </span>
                        <span class="tree-item-icon icon-folder">
                            <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
                                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
                            </svg>
                        </span>
                        <span class="tree-item-name">${item.name}</span>
                    </div>
                    <div class="tree-children" style="display: none;">
                        ${item.children ? renderFileTree(item.children, level + 1) : ''}
                    </div>
                </div>
            `;
        } else {
            const iconClass = Utils.getFileIcon(item.name);
            return `
                <div class="tree-file" data-path="${item.path}">
                    <div class="tree-item" style="padding-left: ${level * 16 + 24}px">
                        <span class="tree-item-icon ${iconClass}">
                            <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
                                <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"/>
                            </svg>
                        </span>
                        <span class="tree-item-name">${item.name}</span>
                    </div>
                </div>
            `;
        }
    }).join('');
}

// Setup file tree events
function setupFileTreeEvents() {
    // Folder toggle
    document.querySelectorAll('.tree-folder > .tree-item').forEach(item => {
        item.addEventListener('click', () => {
            const folder = item.closest('.tree-folder');
            const children = folder.querySelector('.tree-children');
            const toggle = item.querySelector('.tree-toggle');
            
            if (children.style.display === 'none') {
                children.style.display = 'block';
                toggle.classList.add('expanded');
            } else {
                children.style.display = 'none';
                toggle.classList.remove('expanded');
            }
        });
    });

    // File click to open
    document.querySelectorAll('.tree-file').forEach(file => {
        file.addEventListener('click', () => {
            const path = file.dataset.path;
            openFile(path);
        });
    });
}

// Open a file
async function openFile(path) {
    const { API, UI, Utils } = window.AgentForge;

    // Check if already open
    if (EditorState.openFiles.has(path)) {
        switchToFile(path);
        return;
    }

    try {
        const result = await API.get(`/api/projects/${EditorState.project.id}/files/content/?path=${encodeURIComponent(path)}`);

        if (result.success) {
            // Add to open files
            EditorState.openFiles.set(path, {
                content: result.content,
                modified: false,
            });

            // Create tab
            createTab(path);

            // Switch to file
            switchToFile(path);

            // Hide welcome screen
            document.getElementById('editor-welcome').style.display = 'none';
        } else {
            UI.toast(result.error || 'Failed to open file', 'error');
        }
    } catch (error) {
        UI.toast('Failed to open file', 'error');
    }
}

// Create a tab for a file
function createTab(path) {
    const { Utils } = window.AgentForge;
    const tabs = document.getElementById('editor-tabs');
    const filename = path.split('/').pop();
    const iconClass = Utils.getFileIcon(filename);

    const tab = document.createElement('div');
    tab.className = 'tab';
    tab.dataset.path = path;
    tab.innerHTML = `
        <span class="tab-icon ${iconClass}">
            <svg viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"/>
            </svg>
        </span>
        <span class="tab-name">${filename}</span>
        <button class="tab-close">
            <svg viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"/>
            </svg>
        </button>
    `;

    // Tab click
    tab.addEventListener('click', (e) => {
        if (!e.target.closest('.tab-close')) {
            switchToFile(path);
        }
    });

    // Close button
    tab.querySelector('.tab-close').addEventListener('click', (e) => {
        e.stopPropagation();
        closeFile(path);
    });

    tabs.appendChild(tab);
}

// Switch to a file
function switchToFile(path) {
    const { Utils } = window.AgentForge;
    const file = EditorState.openFiles.get(path);
    
    if (!file) return;

    // Update active tab
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.path === path);
    });

    // Update active file in tree
    document.querySelectorAll('.tree-file').forEach(item => {
        item.querySelector('.tree-item').classList.toggle('active', item.dataset.path === path);
    });

    // Update editor
    const language = Utils.getLanguage(path);
    const model = monaco.editor.createModel(file.content, language);
    EditorState.editor.setModel(model);

    EditorState.currentFile = path;
    EditorState.activeTab = path;
}

// Close a file
function closeFile(path) {
    const { UI } = window.AgentForge;
    const file = EditorState.openFiles.get(path);

    if (file && file.modified) {
        if (!confirm('This file has unsaved changes. Close anyway?')) {
            return;
        }
    }

    // Remove from open files
    EditorState.openFiles.delete(path);

    // Remove tab
    const tab = document.querySelector(`.tab[data-path="${path}"]`);
    if (tab) {
        tab.remove();
    }

    // If this was the active file, switch to another
    if (EditorState.currentFile === path) {
        const remaining = Array.from(EditorState.openFiles.keys());
        if (remaining.length > 0) {
            switchToFile(remaining[remaining.length - 1]);
        } else {
            EditorState.currentFile = null;
            EditorState.editor.setModel(null);
            document.getElementById('editor-welcome').style.display = 'flex';
        }
    }
}

// Update tab modified state
function updateTabModified(path, modified) {
    const tab = document.querySelector(`.tab[data-path="${path}"]`);
    if (tab) {
        let indicator = tab.querySelector('.tab-modified');
        if (modified && !indicator) {
            indicator = document.createElement('span');
            indicator.className = 'tab-modified';
            tab.querySelector('.tab-name').after(indicator);
        } else if (!modified && indicator) {
            indicator.remove();
        }
    }
}

// Save current file
async function saveCurrentFile() {
    const { API, UI } = window.AgentForge;

    if (!EditorState.currentFile) return;

    const file = EditorState.openFiles.get(EditorState.currentFile);
    if (!file) return;

    try {
        const content = EditorState.editor.getValue();
        const result = await API.post(`/api/projects/${EditorState.project.id}/files/save/`, {
            path: EditorState.currentFile,
            content: content,
        });

        if (result.success) {
            file.content = content;
            file.modified = false;
            updateTabModified(EditorState.currentFile, false);
            UI.toast('File saved', 'success');
        } else {
            UI.toast(result.error || 'Failed to save file', 'error');
        }
    } catch (error) {
        UI.toast('Failed to save file', 'error');
    }
}

// Run current file
async function runCurrentFile() {
    const { API, UI } = window.AgentForge;
    const output = document.getElementById('terminal-output');
    const terminalPanel = document.getElementById('terminal-panel');

    if (!EditorState.currentFile) {
        UI.toast('No file open to run', 'warning');
        return;
    }

    // Show terminal panel if collapsed
    terminalPanel.classList.remove('collapsed');

    // Save file first if modified
    const file = EditorState.openFiles.get(EditorState.currentFile);
    if (file && file.modified) {
        await saveCurrentFile();
    }

    // Show running message
    output.innerHTML = `<div class="output-command">$ Running ${EditorState.currentFile}...</div>`;

    try {
        const result = await API.post(`/api/projects/${EditorState.project.id}/files/run/`, {
            path: EditorState.currentFile,
        });

        // Handle HTML preview
        if (result.type === 'html_preview') {
            output.innerHTML = `
                <div class="output-command">$ Preview ${EditorState.currentFile}</div>
                <div class="output-success">✓ ${result.message}</div>
                <div class="output-info">Opening preview in new tab...</div>
            `;
            // Open the HTML file content in a new tab using data URI
            const content = EditorState.editor.getValue();
            const blob = new Blob([content], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            window.open(url, '_blank');
            UI.toast('HTML preview opened in new tab', 'success');
            return;
        }

        // Format output
        let html = `<div class="output-command">$ ${result.command || 'run ' + EditorState.currentFile}</div>`;
        
        if (result.stdout) {
            html += `<div class="output-line">${escapeHtml(result.stdout)}</div>`;
        }
        
        if (result.stderr) {
            html += `<div class="output-line output-error">${escapeHtml(result.stderr)}</div>`;
        }
        
        if (result.success) {
            html += `<div class="output-success">✓ Process exited with code ${result.exit_code || 0}</div>`;
        } else if (result.error) {
            html += `<div class="output-error">✗ ${result.error}</div>`;
        } else {
            html += `<div class="output-error">✗ Process exited with code ${result.exit_code || 1}</div>`;
        }
        
        output.innerHTML = html;

    } catch (error) {
        output.innerHTML = `<div class="output-error">Error: ${error.message || 'Failed to run file'}</div>`;
    }
}

// Helper to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Setup general event listeners
function setupEventListeners() {
    const { API, UI } = window.AgentForge;

    // Collapse sidebar
    document.getElementById('collapse-sidebar')?.addEventListener('click', () => {
        document.getElementById('file-sidebar').classList.toggle('collapsed');
    });

    // Collapse agent panel
    document.getElementById('collapse-panel')?.addEventListener('click', () => {
        document.getElementById('agent-panel').classList.toggle('collapsed');
    });

    // Save button
    document.getElementById('save-btn')?.addEventListener('click', saveCurrentFile);

    // Index button
    document.getElementById('index-btn')?.addEventListener('click', async () => {
        UI.toast('Indexing project...', 'info');
        try {
            const result = await API.post(`/api/projects/${EditorState.project.id}/index/`);
            if (result.success) {
                UI.toast(`Indexed ${result.document_count || 0} files`, 'success');
                // Update status
                const status = document.getElementById('project-status');
                status.innerHTML = '<span class="status-dot status-success"></span>Indexed';
            } else {
                UI.toast(result.error || 'Indexing failed', 'error');
            }
        } catch (error) {
            UI.toast('Indexing failed', 'error');
        }
    });

    // Run button
    document.getElementById('run-btn')?.addEventListener('click', runCurrentFile);
    
    // F5 keyboard shortcut for Run
    document.addEventListener('keydown', (e) => {
        if (e.key === 'F5') {
            e.preventDefault();
            runCurrentFile();
        }
    });

    // Terminal controls
    document.getElementById('toggle-terminal')?.addEventListener('click', () => {
        document.getElementById('terminal-panel').classList.toggle('collapsed');
    });
    
    document.getElementById('clear-terminal')?.addEventListener('click', () => {
        const output = document.getElementById('terminal-output');
        output.innerHTML = '<div class="terminal-welcome">Terminal cleared</div>';
    });

    // Terminal tabs
    document.querySelectorAll('.terminal-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.terminal-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
        });
    });

    // New file button
    document.getElementById('new-file-btn')?.addEventListener('click', () => {
        UI.showModal('new-file-modal');
        document.getElementById('new-file-path').focus();
    });

    // New file modal
    document.getElementById('new-file-modal-close')?.addEventListener('click', () => {
        UI.hideModal('new-file-modal');
    });
    document.getElementById('new-file-cancel')?.addEventListener('click', () => {
        UI.hideModal('new-file-modal');
    });

    document.getElementById('new-file-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const path = document.getElementById('new-file-path').value.trim();
        
        if (!path) return;

        try {
            const result = await API.post(`/api/projects/${EditorState.project.id}/files/create/`, {
                path: path,
                content: '',
            });

            if (result.success) {
                UI.hideModal('new-file-modal');
                document.getElementById('new-file-form').reset();
                await loadFileTree();
                openFile(path);
            } else {
                UI.toast(result.error || 'Failed to create file', 'error');
            }
        } catch (error) {
            UI.toast('Failed to create file', 'error');
        }
    });

    // Diff modal
    document.getElementById('diff-modal-close')?.addEventListener('click', () => {
        UI.hideModal('diff-modal');
    });
    document.getElementById('diff-cancel')?.addEventListener('click', () => {
        UI.hideModal('diff-modal');
    });
}

// Setup chat functionality
function setupChat() {
    const { API, UI, Utils } = window.AgentForge;

    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('send-btn');

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });

    // Submit on Enter (Shift+Enter for new line)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // Suggestion buttons
    document.querySelectorAll('.suggestion-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            chatInput.value = btn.dataset.prompt + ' ';
            chatInput.focus();
        });
    });

    // Submit chat
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const message = chatInput.value.trim();
        if (!message) return;

        // Add user message to chat
        addMessage('user', message);
        chatInput.value = '';
        chatInput.style.height = 'auto';

        // Show loading
        const loadingEl = addMessage('assistant', null, true);

        // Disable input
        sendBtn.disabled = true;

        try {
            const result = await API.post(`/api/projects/${EditorState.project.id}/chat/`, {
                message: message,
                session_id: EditorState.sessionId,
            });

            // Remove loading
            loadingEl.remove();

            if (result.success) {
                EditorState.sessionId = result.session_id;
                addMessage('assistant', result.response);

                // Handle pending changes
                if (result.pending_changes && result.pending_changes.length > 0) {
                    showPendingChanges(result.pending_changes);
                }
            } else {
                addMessage('assistant', `Error: ${result.error || 'Something went wrong'}`);
            }
        } catch (error) {
            loadingEl.remove();
            addMessage('assistant', `Error: ${error.message || 'Failed to send message'}`);
        } finally {
            sendBtn.disabled = false;
            chatInput.focus();
        }
    });

    // Change action buttons
    setupChangeActions();
}

// Add message to chat
function addMessage(role, content, loading = false) {
    const chatMessages = document.getElementById('chat-messages');
    
    // Hide welcome if present
    const welcome = chatMessages.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const messageEl = document.createElement('div');
    messageEl.className = `message message-${role}`;

    const avatarSvg = role === 'user'
        ? '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"/></svg>'
        : '<svg viewBox="0 0 20 20" fill="currentColor"><path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z"/></svg>';

    if (loading) {
        messageEl.innerHTML = `
            <div class="message-avatar">${avatarSvg}</div>
            <div class="message-content">
                <div class="message-loading">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
    } else {
        messageEl.innerHTML = `
            <div class="message-avatar">${avatarSvg}</div>
            <div class="message-content">${formatMessageContent(content)}</div>
        `;
    }

    chatMessages.appendChild(messageEl);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return messageEl;
}

// Format message content (simple markdown)
function formatMessageContent(content) {
    if (!content) return '';
    
    return content
        // Code blocks
        .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        // Inline code
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Bold
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        // Line breaks
        .replace(/\n/g, '<br>');
}

// Show pending changes
function showPendingChanges(changes) {
    const container = document.getElementById('pending-changes');
    const list = document.getElementById('changes-list');
    const count = document.getElementById('pending-count');

    container.style.display = 'block';
    count.textContent = changes.length;

    list.innerHTML = changes.map(change => `
        <div class="change-item" data-change-id="${change.id}">
            <div class="change-info">
                <span class="change-type change-type-${change.type}">${change.type}</span>
                <span class="change-file">${change.file}</span>
            </div>
            <div class="change-actions">
                <button class="btn btn-icon btn-success preview-change-btn" title="Preview">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/>
                        <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z"/>
                    </svg>
                </button>
                <button class="btn btn-icon btn-success apply-change-btn" title="Apply">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"/>
                    </svg>
                </button>
                <button class="btn btn-icon btn-danger reject-change-btn" title="Reject">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"/>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');

    setupChangeActions();
}

// Setup change action buttons
function setupChangeActions() {
    const { API, UI } = window.AgentForge;

    // Preview buttons
    document.querySelectorAll('.preview-change-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const changeItem = btn.closest('.change-item');
            const changeId = changeItem.dataset.changeId;

            try {
                const result = await API.get(`/api/projects/${EditorState.project.id}/changes/${changeId}/preview/`);
                
                if (result.success) {
                    showDiffModal(result);
                }
            } catch (error) {
                UI.toast('Failed to load preview', 'error');
            }
        });
    });

    // Apply buttons
    document.querySelectorAll('.apply-change-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const changeItem = btn.closest('.change-item');
            const changeId = changeItem.dataset.changeId;

            try {
                const result = await API.post(`/api/projects/${EditorState.project.id}/changes/${changeId}/apply/`);
                
                if (result.success) {
                    UI.toast('Change applied', 'success');
                    changeItem.remove();
                    updatePendingCount();
                    await loadFileTree();
                }
            } catch (error) {
                UI.toast('Failed to apply change', 'error');
            }
        });
    });

    // Reject buttons
    document.querySelectorAll('.reject-change-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const changeItem = btn.closest('.change-item');
            const changeId = changeItem.dataset.changeId;

            try {
                const result = await API.post(`/api/projects/${EditorState.project.id}/changes/${changeId}/reject/`);
                
                if (result.success) {
                    UI.toast('Change rejected', 'info');
                    changeItem.remove();
                    updatePendingCount();
                }
            } catch (error) {
                UI.toast('Failed to reject change', 'error');
            }
        });
    });
}

// Update pending changes count
function updatePendingCount() {
    const list = document.getElementById('changes-list');
    const count = document.getElementById('pending-count');
    const container = document.getElementById('pending-changes');
    
    const remaining = list.querySelectorAll('.change-item').length;
    count.textContent = remaining;
    
    if (remaining === 0) {
        container.style.display = 'none';
    }
}

// Show diff modal
function showDiffModal(data) {
    const { UI, Utils } = window.AgentForge;

    const fileInfo = document.getElementById('diff-file-info');
    const diffView = document.getElementById('diff-view');

    fileInfo.textContent = data.file_path;

    // Format diff
    if (data.diff) {
        diffView.innerHTML = `<pre>${formatDiff(data.diff)}</pre>`;
    } else {
        // Show side-by-side if no diff
        diffView.innerHTML = `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div>
                    <h4 style="font-size: 12px; color: var(--color-text-muted); margin-bottom: 8px;">Original</h4>
                    <pre style="font-size: 12px;">${Utils.escapeHtml(data.original || '(empty)')}</pre>
                </div>
                <div>
                    <h4 style="font-size: 12px; color: var(--color-text-muted); margin-bottom: 8px;">New</h4>
                    <pre style="font-size: 12px;">${Utils.escapeHtml(data.new || '(empty)')}</pre>
                </div>
            </div>
        `;
    }

    UI.showModal('diff-modal');
}

// Format diff with syntax highlighting
function formatDiff(diff) {
    const { Utils } = window.AgentForge;
    
    return diff.split('\n').map(line => {
        let className = 'diff-context';
        if (line.startsWith('+') && !line.startsWith('+++')) {
            className = 'diff-add';
        } else if (line.startsWith('-') && !line.startsWith('---')) {
            className = 'diff-remove';
        } else if (line.startsWith('@@')) {
            className = 'diff-header';
        }
        return `<span class="diff-line ${className}">${Utils.escapeHtml(line)}</span>`;
    }).join('\n');
}
