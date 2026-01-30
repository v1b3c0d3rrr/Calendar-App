# Calendar App

A simple, accessible monthly calendar built with vanilla JavaScript. Add, edit, and delete events with automatic localStorage persistence. No frameworks, no build tools - just open and use.

## Features

- Monthly calendar view with previous/next month navigation
- Add events by clicking any day
- Edit existing events by clicking on event pills
- Delete events when no longer needed
- Automatic data persistence using browser localStorage
- Fully responsive design (works on mobile, tablet, and desktop)
- Keyboard navigation support
- Screen reader friendly with proper ARIA labels
- Today's date highlighted automatically
- Real-time form validation

## Quick Start

### Prerequisites

- A modern web browser (Chrome, Firefox, Safari, Edge)
- That's it! No installation needed.

### Running the App

1. Download or clone this repository to your computer.

2. Open the `index.html` file in your web browser. You can:
   - Double-click `index.html` in your file manager, or
   - Right-click `index.html` and choose "Open with" your browser, or
   - Drag `index.html` into an open browser window

3. The calendar should appear immediately, showing the current month with today's date highlighted.

**Note:** Your events are saved automatically in your browser's localStorage. They will persist even if you close the browser, but they are specific to the browser you're using.

## How to Use

### Adding an Event

1. Click on any day in the calendar
2. A modal will appear with a form
3. Fill in the event details:
   - **Title** (required): Name your event
   - **Date** (required): Pre-filled with the day you clicked
   - **Description** (optional): Add extra details
4. Click "Save Event"

The event will appear as a colored pill on that day.

### Editing an Event

1. Click on an event pill (the colored label showing the event title)
2. The same modal opens with the event details filled in
3. Make your changes
4. Click "Save Event" to update

### Deleting an Event

1. Click on the event pill to open it for editing
2. Click the "Delete" button at the bottom of the form
3. The event will be removed immediately

### Navigating Months

- Click the **left arrow** button in the header to go to the previous month
- Click the **right arrow** button to go to the next month
- The calendar automatically shows days from adjacent months in a lighter color

### Keyboard Navigation

- Press **Tab** to move between days and events
- Press **Enter** or **Space** on any day to add an event
- Press **Enter** or **Space** on an event pill to edit it
- Press **Escape** to close the modal
- Use **Tab** and **Shift+Tab** to navigate within the modal

## Project Structure

```
Calendar/
├── index.html      # HTML structure and layout
├── styles.css      # All styling with CSS Grid and responsive design
├── app.js          # Application logic and event handling
└── README.md       # This file
```

### File Descriptions

- **index.html**: Contains the calendar layout, modal dialog for events, and form elements. Uses semantic HTML with ARIA roles for accessibility.

- **styles.css**: Defines the visual appearance using CSS Grid for the calendar layout. Includes responsive breakpoints for mobile (480px) and tablet (768px) devices. Uses CSS custom properties for easy theming.

- **app.js**: Implements all functionality using the module pattern. Handles calendar rendering, event CRUD operations, localStorage persistence, form validation, and keyboard navigation.

## Technologies Used

- **HTML5**: Semantic markup with accessibility features
- **CSS3**: Modern styling with CSS Grid, Flexbox, and custom properties
- **Vanilla JavaScript**: No frameworks or libraries - pure ES6+ JavaScript
- **localStorage API**: Browser-based data persistence
- **Module Pattern**: Clean code organization without external dependencies

## Accessibility Features

This calendar follows web accessibility best practices:

- **Keyboard Navigation**: Fully operable without a mouse
- **ARIA Roles**: Proper roles for screen readers (grid, gridcell, dialog)
- **Focus Management**: Automatic focus restoration after modal close
- **Focus Trap**: Keeps focus inside modal when open
- **Descriptive Labels**: Each day announces full date to screen readers
- **Color Contrast**: Meets WCAG AA standards
- **Reduced Motion**: Respects user's motion preferences
- **Minimum Touch Targets**: 44x44px buttons for easy tapping

## Browser Compatibility

Works in all modern browsers that support:
- CSS Grid (2017+)
- ES6 JavaScript (2015+)
- localStorage API

Tested in:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Data Storage

Events are stored in your browser's localStorage under the key `calendarEvents`. This means:

- Data persists between browser sessions
- Data is stored locally (not sent to any server)
- Each browser has its own separate data
- Clearing browser data will delete your events
- No account or internet connection required

## Customization

To customize colors, edit the CSS custom properties in `styles.css` at the top:

```css
:root {
  --primary-color: #4f46e5;  /* Main accent color */
  --danger-color: #dc2626;   /* Delete button color */
  --bg-color: #f8fafc;       /* Background color */
  /* ...and more */
}
```

## Known Limitations

- Events are stored per-browser (not synced across devices)
- No recurring event support
- Single-day events only (no multi-day events)
- No event time (only dates)
- No event categories or colors
- No export/import functionality

## Troubleshooting

**Events aren't saving:**
- Check if your browser allows localStorage
- Check if you're in private/incognito mode (localStorage may not persist)
- Try a different browser

**Calendar looks broken:**
- Make sure you're using a modern browser
- Check if CSS loaded correctly (styles.css in same folder as index.html)
- Try hard-refreshing the page (Ctrl+F5 or Cmd+Shift+R)

**Modal won't close:**
- Press Escape key
- Click outside the modal on the dark overlay
- Check browser console for JavaScript errors (F12)

## Contributing

This is a simple educational project. Feel free to fork and modify for your own use.

## License

Free to use and modify as you wish.
