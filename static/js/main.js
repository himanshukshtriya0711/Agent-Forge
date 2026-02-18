/* =============================================================================
   AgentForge - Main JavaScript
   Common utilities and helpers
   ============================================================================= */

// API Helper
const API = {
    // Get CSRF token from meta tag
    getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    },

    // Make API request
    async request(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
        };

        const mergedOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers,
            },
        };

        try {
            const response = await fetch(url, mergedOptions);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Request failed');
            }
            
            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    get(url) {
        return this.request(url, { method: 'GET' });
    },

    post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    delete(url) {
        return this.request(url, { method: 'DELETE' });
    },
};

// UI Helper
const UI = {
    // Show/hide modal
    showModal(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },

    hideModal(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        }
    },

    // Toast notification
    toast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span>${message}</span>
            <button class="toast-close">&times;</button>
        `;
        
        // Add styles if not present
        if (!document.getElementById('toast-styles')) {
            const styles = document.createElement('style');
            styles.id = 'toast-styles';
            styles.textContent = `
                .toast {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    padding: 12px 16px;
                    background: var(--color-bg-secondary);
                    border: 1px solid var(--color-border);
                    border-radius: var(--radius-lg);
                    box-shadow: var(--shadow-lg);
                    z-index: 9999;
                    animation: slideIn 0.3s ease;
                }
                .toast-success { border-color: var(--color-success); }
                .toast-error { border-color: var(--color-danger); }
                .toast-warning { border-color: var(--color-warning); }
                .toast-close {
                    background: none;
                    border: none;
                    color: var(--color-text-muted);
                    cursor: pointer;
                    font-size: 18px;
                }
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
            `;
            document.head.appendChild(styles);
        }
        
        document.body.appendChild(toast);
        
        // Close button
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.remove();
        });
        
        // Auto remove after 5s
        setTimeout(() => {
            toast.remove();
        }, 5000);
    },

    // Confirm dialog
    confirm(message) {
        return new Promise((resolve) => {
            resolve(window.confirm(message));
        });
    },
};

// Utils
const Utils = {
    // Debounce
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Format file size
    formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    },

    // Get file extension
    getFileExtension(filename) {
        return filename.slice((filename.lastIndexOf('.') - 1 >>> 0) + 2);
    },

    // Get file icon based on extension
    getFileIcon(filename) {
        const ext = this.getFileExtension(filename).toLowerCase();
        const icons = {
            py: 'icon-python',
            js: 'icon-javascript',
            ts: 'icon-typescript',
            jsx: 'icon-javascript',
            tsx: 'icon-typescript',
            html: 'icon-html',
            css: 'icon-css',
            json: 'icon-json',
            md: 'icon-markdown',
        };
        return icons[ext] || 'icon-default';
    },

    // Get language for Monaco
    getLanguage(filename) {
        const ext = this.getFileExtension(filename).toLowerCase();
        const languages = {
            py: 'python',
            js: 'javascript',
            ts: 'typescript',
            jsx: 'javascript',
            tsx: 'typescript',
            html: 'html',
            css: 'css',
            json: 'json',
            md: 'markdown',
            yml: 'yaml',
            yaml: 'yaml',
            sh: 'shell',
            bash: 'shell',
            sql: 'sql',
            xml: 'xml',
        };
        return languages[ext] || 'plaintext';
    },

    // Escape HTML
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// Initialize modal close handlers
document.addEventListener('DOMContentLoaded', () => {
    // Close modal on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', () => {
            const modal = overlay.closest('.modal');
            if (modal) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });

    // Close modal on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.active').forEach(modal => {
                modal.classList.remove('active');
            });
            document.body.style.overflow = '';
        }
    });
});

// Export for use in other scripts
window.AgentForge = { API, UI, Utils };
