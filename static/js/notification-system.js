/**
 * Modern Notification System
 * Provides sleek, glassmorphism-styled notifications that align with the dark theme
 */

class NotificationSystem {
    constructor() {
        this.container = null;
        this.notifications = [];
        this.maxNotifications = 5;
        this.defaultDuration = 4000; // 4 seconds
        this.init();
    }

    init() {
        // Create notification container if it doesn't exist
        this.container = document.querySelector('.notification-container');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'notification-container';
            document.body.appendChild(this.container);
        }
    }

    /**
     * Show a notification
     * @param {Object} options - Notification options
     * @param {string} options.type - 'success', 'error', 'info', 'warning'
     * @param {string} options.title - Notification title
     * @param {string} options.message - Notification message
     * @param {number} options.duration - Auto-hide duration in ms (0 = no auto-hide)
     * @param {boolean} options.closable - Whether to show close button
     */
    show(options = {}) {
        const {
            type = 'info',
            title = '',
            message = '',
            duration = this.defaultDuration,
            closable = true
        } = options;

        // Remove oldest notification if we've reached the limit
        if (this.notifications.length >= this.maxNotifications) {
            this.remove(this.notifications[0]);
        }

        // Create notification element
        const notification = this.createNotificationElement({
            type,
            title,
            message,
            closable,
            duration
        });

        // Add to container and track
        this.container.appendChild(notification);
        this.notifications.push(notification);

        // Show animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);

        // Auto-hide if duration is specified
        if (duration > 0) {
            notification.classList.add('auto-hide');
            
            // Set progress bar animation
            const progressBar = notification.querySelector('.notification-progress-bar');
            if (progressBar) {
                progressBar.style.animationDuration = duration + 'ms';
            }

            setTimeout(() => {
                this.remove(notification);
            }, duration);
        }

        return notification;
    }

    createNotificationElement({ type, title, message, closable, duration }) {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;

        // Get icon based on type
        const icon = this.getIcon(type);

        notification.innerHTML = `
            <div class="notification-body">
                <div class="notification-icon">${icon}</div>
                <div class="notification-content">
                    ${title ? `<div class="notification-title">${title}</div>` : ''}
                    ${message ? `<div class="notification-message">${message}</div>` : ''}
                </div>
            </div>
            ${closable ? '<button class="notification-close" aria-label="Close notification">×</button>' : ''}
            ${duration > 0 ? '<div class="notification-progress"><div class="notification-progress-bar"></div></div>' : ''}
        `;

        // Add close button functionality
        if (closable) {
            const closeBtn = notification.querySelector('.notification-close');
            closeBtn.addEventListener('click', () => {
                this.remove(notification);
            });
        }

        // Add click functionality to dismiss
        notification.addEventListener('click', (e) => {
            if (!e.target.closest('.notification-close')) {
                this.remove(notification);
            }
        });

        return notification;
    }

    getIcon(type) {
        const icons = {
            success: '✓',
            error: '✗',
            warning: '⚠',
            info: 'ℹ'
        };
        return icons[type] || icons.info;
    }

    remove(notification) {
        if (!notification || !this.notifications.includes(notification)) {
            return;
        }

        // Hide animation
        notification.classList.remove('show');
        notification.classList.add('hide');

        // Remove from DOM after animation
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
            
            // Remove from tracking array
            const index = this.notifications.indexOf(notification);
            if (index > -1) {
                this.notifications.splice(index, 1);
            }
        }, 400);
    }

    // Convenience methods for different notification types
    success(title, message, options = {}) {
        return this.show({ ...options, type: 'success', title, message });
    }

    error(title, message, options = {}) {
        return this.show({ ...options, type: 'error', title, message });
    }

    info(title, message, options = {}) {
        return this.show({ ...options, type: 'info', title, message });
    }

    warning(title, message, options = {}) {
        return this.show({ ...options, type: 'warning', title, message });
    }

    // Clear all notifications
    clear() {
        [...this.notifications].forEach(notification => {
            this.remove(notification);
        });
    }
}

// Create global instance
const notificationSystem = new NotificationSystem();

// Make it globally available
window.NotificationSystem = NotificationSystem;
window.showNotification = (options) => notificationSystem.show(options);
window.notifySuccess = (title, message, options) => notificationSystem.success(title, message, options);
window.notifyError = (title, message, options) => notificationSystem.error(title, message, options);
window.notifyInfo = (title, message, options) => notificationSystem.info(title, message, options);
window.notifyWarning = (title, message, options) => notificationSystem.warning(title, message, options);

// Legacy alert replacement (for backward compatibility)
window.modernAlert = (message, type = 'info') => {
    notificationSystem.show({
        type,
        title: type.charAt(0).toUpperCase() + type.slice(1),
        message,
        duration: 3000
    });
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = NotificationSystem;
}
