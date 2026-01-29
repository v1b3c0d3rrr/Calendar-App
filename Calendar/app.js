/**
 * Calendar App
 * A simple monthly calendar with event management and localStorage persistence.
 */

const CalendarApp = (function() {
  // State
  let currentDate = new Date();
  let events = [];
  let editingEventId = null;

  // DOM Elements
  const monthYearEl = document.getElementById('monthYear');
  const calendarGridEl = document.getElementById('calendarGrid');
  const prevMonthBtn = document.getElementById('prevMonth');
  const nextMonthBtn = document.getElementById('nextMonth');
  const modalOverlay = document.getElementById('modalOverlay');
  const modalTitle = document.getElementById('modalTitle');
  const eventForm = document.getElementById('eventForm');
  const eventTitleInput = document.getElementById('eventTitle');
  const eventDateInput = document.getElementById('eventDate');
  const eventDescriptionInput = document.getElementById('eventDescription');
  const eventIdInput = document.getElementById('eventId');
  const titleError = document.getElementById('titleError');
  const dateError = document.getElementById('dateError');
  const deleteBtn = document.getElementById('deleteBtn');
  const modalCloseBtn = document.getElementById('modalClose');

  // Constants
  const STORAGE_KEY = 'calendarEvents';
  const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  /**
   * Initialize the calendar app
   */
  function init() {
    loadEvents();
    renderCalendar();
    bindEvents();
  }

  /**
   * Bind event listeners
   */
  function bindEvents() {
    prevMonthBtn.addEventListener('click', () => navigateMonth(-1));
    nextMonthBtn.addEventListener('click', () => navigateMonth(1));
    modalCloseBtn.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', handleOverlayClick);
    eventForm.addEventListener('submit', handleFormSubmit);
    deleteBtn.addEventListener('click', handleDelete);
    document.addEventListener('keydown', handleKeydown);

    // Real-time validation
    eventTitleInput.addEventListener('input', () => validateField('title'));
    eventDateInput.addEventListener('change', () => validateField('date'));
  }

  /**
   * Navigate to previous or next month
   */
  function navigateMonth(direction) {
    currentDate.setMonth(currentDate.getMonth() + direction);
    renderCalendar();
  }

  /**
   * Render the calendar grid
   */
  function renderCalendar() {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    // Update header
    monthYearEl.textContent = `${MONTHS[month]} ${year}`;

    // Get first day of month and total days
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startingDay = firstDay.getDay();
    const totalDays = lastDay.getDate();

    // Get previous month's last days
    const prevLastDay = new Date(year, month, 0).getDate();

    // Today's date for comparison
    const today = new Date();
    const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

    // Build calendar cells
    calendarGridEl.innerHTML = '';
    let dayCount = 1;
    let nextMonthDay = 1;

    for (let i = 0; i < 42; i++) {
      const cell = document.createElement('div');
      cell.className = 'calendar-day';

      let cellDate;
      let dayNumber;

      if (i < startingDay) {
        // Previous month days
        dayNumber = prevLastDay - startingDay + i + 1;
        cell.classList.add('other-month');
        cellDate = new Date(year, month - 1, dayNumber);
      } else if (dayCount > totalDays) {
        // Next month days
        dayNumber = nextMonthDay++;
        cell.classList.add('other-month');
        cellDate = new Date(year, month + 1, dayNumber);
      } else {
        // Current month days
        dayNumber = dayCount++;
        cellDate = new Date(year, month, dayNumber);

        if (isCurrentMonth && dayNumber === today.getDate()) {
          cell.classList.add('today');
        }
      }

      const dateStr = formatDate(cellDate);
      cell.dataset.date = dateStr;

      // Day number
      const dayNumberEl = document.createElement('div');
      dayNumberEl.className = 'day-number';
      dayNumberEl.textContent = dayNumber;
      cell.appendChild(dayNumberEl);

      // Events for this day
      const dayEvents = getEventsForDate(dateStr);
      if (dayEvents.length > 0) {
        const eventsContainer = document.createElement('div');
        eventsContainer.className = 'events-container';

        const maxVisible = window.innerWidth <= 480 ? 1 : 2;
        dayEvents.slice(0, maxVisible).forEach(event => {
          const pill = document.createElement('div');
          pill.className = 'event-pill';
          pill.textContent = event.title;
          pill.dataset.eventId = event.id;
          pill.addEventListener('click', (e) => {
            e.stopPropagation();
            openModal(dateStr, event);
          });
          eventsContainer.appendChild(pill);
        });

        if (dayEvents.length > maxVisible) {
          const more = document.createElement('div');
          more.className = 'event-more';
          more.textContent = `+${dayEvents.length - maxVisible} more`;
          eventsContainer.appendChild(more);
        }

        cell.appendChild(eventsContainer);
      }

      // Click handler to add event
      cell.addEventListener('click', () => openModal(dateStr));

      calendarGridEl.appendChild(cell);
    }
  }

  /**
   * Format date as YYYY-MM-DD
   */
  function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  /**
   * Get events for a specific date
   */
  function getEventsForDate(dateStr) {
    return events.filter(event => event.date === dateStr);
  }

  /**
   * Generate a unique ID
   */
  function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  // ==================== localStorage ====================

  /**
   * Load events from localStorage
   */
  function loadEvents() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        events = JSON.parse(stored);
      }
    } catch (e) {
      console.error('Failed to load events from localStorage:', e);
      events = [];
    }
  }

  /**
   * Save events to localStorage
   */
  function saveEvents() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(events));
    } catch (e) {
      console.error('Failed to save events to localStorage:', e);
    }
  }

  // ==================== Modal ====================

  /**
   * Open the modal for adding/editing an event
   */
  function openModal(dateStr, event = null) {
    editingEventId = event ? event.id : null;

    // Update modal title and delete button visibility
    modalTitle.textContent = event ? 'Edit Event' : 'Add Event';
    deleteBtn.classList.toggle('visible', !!event);

    // Populate form
    eventTitleInput.value = event ? event.title : '';
    eventDateInput.value = event ? event.date : dateStr;
    eventDescriptionInput.value = event ? event.description : '';
    eventIdInput.value = event ? event.id : '';

    // Clear errors
    clearErrors();

    // Show modal
    modalOverlay.classList.add('active');

    // Focus on title input
    setTimeout(() => eventTitleInput.focus(), 100);
  }

  /**
   * Close the modal
   */
  function closeModal() {
    modalOverlay.classList.remove('active');
    editingEventId = null;
    eventForm.reset();
    clearErrors();
  }

  /**
   * Handle click on overlay (close if clicking outside modal)
   */
  function handleOverlayClick(e) {
    if (e.target === modalOverlay) {
      closeModal();
    }
  }

  /**
   * Handle keyboard events
   */
  function handleKeydown(e) {
    if (e.key === 'Escape' && modalOverlay.classList.contains('active')) {
      closeModal();
    }
  }

  // ==================== Form Validation ====================

  /**
   * Validate a specific field
   */
  function validateField(field) {
    let isValid = true;

    if (field === 'title') {
      const title = eventTitleInput.value.trim();
      if (!title) {
        titleError.textContent = 'Title is required';
        eventTitleInput.classList.add('error');
        isValid = false;
      } else {
        titleError.textContent = '';
        eventTitleInput.classList.remove('error');
      }
    }

    if (field === 'date') {
      const date = eventDateInput.value;
      if (!date || !isValidDate(date)) {
        dateError.textContent = 'Valid date is required';
        eventDateInput.classList.add('error');
        isValid = false;
      } else {
        dateError.textContent = '';
        eventDateInput.classList.remove('error');
      }
    }

    return isValid;
  }

  /**
   * Validate the entire form
   */
  function validateForm() {
    const titleValid = validateField('title');
    const dateValid = validateField('date');
    return titleValid && dateValid;
  }

  /**
   * Check if date string is valid
   */
  function isValidDate(dateStr) {
    const date = new Date(dateStr);
    return !isNaN(date.getTime());
  }

  /**
   * Clear all error messages
   */
  function clearErrors() {
    titleError.textContent = '';
    dateError.textContent = '';
    eventTitleInput.classList.remove('error');
    eventDateInput.classList.remove('error');
  }

  // ==================== CRUD Operations ====================

  /**
   * Handle form submission
   */
  function handleFormSubmit(e) {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    const eventData = {
      id: editingEventId || generateId(),
      title: eventTitleInput.value.trim(),
      date: eventDateInput.value,
      description: eventDescriptionInput.value.trim()
    };

    if (editingEventId) {
      // Update existing event
      const index = events.findIndex(ev => ev.id === editingEventId);
      if (index !== -1) {
        events[index] = eventData;
      }
    } else {
      // Create new event
      events.push(eventData);
    }

    saveEvents();
    renderCalendar();
    closeModal();
  }

  /**
   * Handle event deletion
   */
  function handleDelete() {
    if (editingEventId) {
      events = events.filter(ev => ev.id !== editingEventId);
      saveEvents();
      renderCalendar();
      closeModal();
    }
  }

  // Public API
  return {
    init
  };
})();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', CalendarApp.init);
