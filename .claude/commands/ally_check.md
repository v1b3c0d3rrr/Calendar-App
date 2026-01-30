# Accessibility Check

Perform an accessibility audit on the specified file or the current project.

## Instructions

1. Read the HTML, CSS, and JavaScript files
2. Check for these accessibility issues:

### HTML
- Missing `alt` attributes on images
- Missing `aria-label` or `aria-labelledby` on interactive elements
- Missing `role` attributes where needed
- Improper heading hierarchy (h1 → h2 → h3)
- Missing `lang` attribute on `<html>`
- Missing form labels
- Missing `id` associations between labels and inputs

### CSS
- Color contrast issues (text vs background)
- Focus indicators missing or removed (`:focus` styles)
- Touch target sizes (minimum 44x44px for mobile)
- Motion/animation without `prefers-reduced-motion` support

### JavaScript
- Focus management in modals/dialogs
- Keyboard navigation support (Tab, Enter, Escape)
- Screen reader announcements for dynamic content
- ARIA state updates (aria-expanded, aria-hidden, etc.)

## Output Format

Provide a report with:
1. **Issues Found** - List each issue with file, line number, and description
2. **Recommendations** - How to fix each issue
3. **Good Practices** - What's already done well
4. **Summary** - Overall accessibility score (Good/Needs Work/Poor)

$ARGUMENTS
