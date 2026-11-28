/**
 * Design System Constants
 * Following industry standards for spacing, typography, and animations
 */

// Spacing Scale (8px base unit - industry standard)
export const SPACING = {
  xs: '0.25rem',    // 4px
  sm: '0.5rem',     // 8px
  md: '1rem',       // 16px
  lg: '1.5rem',     // 24px
  xl: '2rem',       // 32px
  '2xl': '3rem',    // 48px
  '3xl': '4rem',    // 64px
} as const;

// Animation Durations (Material Design)
export const ANIMATION = {
  fast: '150ms',
  normal: '250ms',
  slow: '350ms',
  verySlow: '500ms',
} as const;

// Animation Easings (Cubic Bezier - Material Design)
export const EASING = {
  standard: 'cubic-bezier(0.4, 0.0, 0.2, 1)',
  deceleration: 'cubic-bezier(0.0, 0.0, 0.2, 1)',
  acceleration: 'cubic-bezier(0.4, 0.0, 1, 1)',
  sharp: 'cubic-bezier(0.4, 0.0, 0.6, 1)',
} as const;

// Breakpoints (Mobile-first - Tailwind default)
export const BREAKPOINTS = {
  sm: '640px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
  '2xl': '1536px',
} as const;

// Z-Index Scale (Avoid conflicts)
export const Z_INDEX = {
  base: 0,
  dropdown: 1000,
  sticky: 1100,
  overlay: 1200,
  modal: 1300,
  popover: 1400,
  toast: 1500,
  tooltip: 1600,
} as const;

// API Constants
export const API_TIMEOUT = 30000; // 30 seconds
export const DEBOUNCE_DELAY = 300; // 300ms for search inputs
export const THROTTLE_DELAY = 1000; // 1s for scroll/resize

// Accessibility
export const A11Y = {
  minTouchTarget: '44px', // WCAG 2.1 AA minimum
  focusRingWidth: '2px',
  focusRingOffset: '2px',
} as const;

// Swiggy Brand Colors (from your existing theme)
export const COLORS = {
  swiggyOrange: 'hsl(25, 95%, 53%)',
  swiggyOrangeDark: 'hsl(25, 90%, 48%)',
  swiggyGreen: 'hsl(142, 71%, 45%)',
  swiggyRed: 'hsl(0, 84%, 60%)',
  swiggyDark: 'hsl(216, 28%, 17%)',
  swiggyGray: 'hsl(220, 9%, 46%)',
  swiggyLightGray: 'hsl(220, 13%, 95%)',
} as const;
