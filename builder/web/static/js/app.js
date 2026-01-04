// Common utilities and helpers

// Format duration from seconds to human-readable
function formatDuration(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
}

// Format timestamp
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString();
}

// Show toast notification (if we add Bootstrap toasts)
function showNotification(message, type = 'info') {
    // Simple console log for now, can be enhanced with toasts
    console.log(`[${type.toUpperCase()}] ${message}`);
}

// API error handler
function handleAPIError(error) {
    console.error('API Error:', error);
    return {
        error: true,
        message: error.message || 'An error occurred'
    };
}

// Export for use in other scripts
window.ASU = {
    formatDuration,
    formatTimestamp,
    showNotification,
    handleAPIError
};
