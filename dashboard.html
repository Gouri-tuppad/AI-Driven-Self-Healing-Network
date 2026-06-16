/**
 * Client Node Monitoring & Heartbeat System
 * 
 * This script tracks:
 * 1. Periodic heartbeat (every 30 seconds) - proves browser is alive
 * 2. User activity (clicks, form submissions) - tracks actual interactions
 * 
 * Used for client monitoring on admin dashboard:
 * - ACTIVE: Recent activity + heartbeat
 * - INACTIVE: Heartbeat but no activity (user idle)
 * - NODE_FAILURE: No heartbeat for extended period (connection lost)
 */

(function(){
  'use strict';
  
  // Hide admin network banner on student exam page
  const banner = document.getElementById('network-banner');
  if (banner) banner.style.display = 'none';
  
  // Configuration
  const CONFIG = {
    HEARTBEAT_INTERVAL: 30000,  // Send heartbeat every 30 seconds
    HEARTBEAT_ENDPOINT: '/api/heartbeat/',
    ACTIVITY_ENDPOINT: '/api/activity/',
    FIRST_HEARTBEAT_DELAY: 5000  // Delay to ensure session is ready
  };
  
  /**
   * Get CSRF token from cookies
   */
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  
  /**
   * Send heartbeat to server
   * Indicates browser/client is still connected
   */
  async function sendHeartbeat() {
    try {
      const response = await fetch(CONFIG.HEARTBEAT_ENDPOINT, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || ''
        },
        body: JSON.stringify({ type: 'heartbeat' })
      });
      
      if (!response.ok) {
        console.warn(`Heartbeat failed with status ${response.status}`);
      }
    } catch (error) {
      console.warn('Heartbeat error:', error);
    }
  }
  
  /**
   * Track user activity
   * Called when user actively does something
   */
  async function trackActivity(activityType) {
    try {
      const response = await fetch(CONFIG.ACTIVITY_ENDPOINT, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || ''
        },
        body: JSON.stringify({ 
          type: activityType || 'interaction',
          timestamp: new Date().toISOString()
        })
      });
      
      if (!response.ok) {
        console.warn(`Activity tracking failed with status ${response.status}`);
      }
    } catch (error) {
      console.warn('Activity tracking error:', error);
    }
  }
  
  /**
   * Attach activity listeners to track user interactions
   */
  function setupActivityTracking() {
    // Track form submissions (exam answers, etc)
    document.addEventListener('submit', function() {
      trackActivity('form_submit');
    }, true);
    
    // Track button clicks (especially important for exam actions)
    document.addEventListener('click', function(event) {
      const target = event.target.closest('button, a[href], input[type="button"], input[type="submit"]');
      if (target) {
        trackActivity('user_click');
      }
    }, true);
    
    // Track keyboard input (typing answers, etc)
    let keyboardTimeout;
    document.addEventListener('keydown', function() {
      if (keyboardTimeout) clearTimeout(keyboardTimeout);
      keyboardTimeout = setTimeout(() => {
        trackActivity('keyboard_input');
      }, 2000);  // Debounce keyboard events
    }, true);
    
    // Track focus on input fields
    document.addEventListener('focus', function(event) {
      if (event.target.matches('input, textarea, select')) {
        trackActivity('user_focus');
      }
    }, true);
  }
  
  /**
   * Start heartbeat mechanism
   * Initial delay to ensure session is established
   */
  function startHeartbeat() {
    // Send first heartbeat after delay
    setTimeout(() => {
      sendHeartbeat();
      // Then send periodic heartbeats
      setInterval(sendHeartbeat, CONFIG.HEARTBEAT_INTERVAL);
    }, CONFIG.FIRST_HEARTBEAT_DELAY);
  }
  
  /**
   * Initialize monitoring system
   */
  function init() {
    // Only run on exam/student pages (not admin)
    if (!document.body.classList.contains('exam-page') && 
        window.location.pathname.indexOf('admin') !== -1) {
      return;
    }
    
    // Setup activity tracking
    setupActivityTracking();
    
    // Start heartbeat mechanism
    startHeartbeat();
    
    console.log('Client node monitoring initialized');
  }
  
  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  
})();
