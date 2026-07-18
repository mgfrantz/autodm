/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // DnD-themed palette
        parchment: {
          50: '#fdfbf7',
          100: '#f5efe0',
          200: '#e8dcc0',
          300: '#d4c19a',
          400: '#bda374',
          500: '#a38656',
          600: '#826b42',
          700: '#635134',
          800: '#4a3d28',
          900: '#332a1c',
        },
        blood: {
          400: '#a83232',
          500: '#8b1a1a',
          600: '#7a1515',
          700: '#651010',
          800: '#4d0c0c',
          900: '#330707',
        },
        arcane: {
          300: '#7a6bc4',
          400: '#6354b0',
          500: '#4a3b8a',
          600: '#3d3080',
          700: '#322569',
          800: '#261c4d',
          900: '#1a1333',
        },
        leaf: {
          400: '#4f8f4f',
          500: '#3f7a3f',
          600: '#2f6b2f',
          700: '#265526',
        },
        gold: {
          400: '#d4af37',
          500: '#c19a2e',
          600: '#a8841f',
        },
      },
      fontFamily: {
        fantasy: ['"Cinzel"', 'serif'],
        body: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          '0%': { opacity: '0', transform: 'translateX(24px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'overlay-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        // HP-bar shake — plays once when a damage card mounts (UI polish).
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '15%': { transform: 'translateX(-3px)' },
          '30%': { transform: 'translateX(3px)' },
          '45%': { transform: 'translateX(-2px)' },
          '60%': { transform: 'translateX(2px)' },
          '75%': { transform: 'translateX(-1px)' },
        },
        // Collapsed-card expand/collapse chevron nudge.
        'chevron-down': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(1px)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.4s ease-out',
        'slide-up': 'slide-up 0.4s ease-out both',
        'slide-in-right': 'slide-in-right 0.3s ease-out both',
        'scale-in': 'scale-in 0.25s ease-out both',
        'overlay-in': 'overlay-in 0.2s ease-out',
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        // One-shot feedback animations (respect prefers-reduced-motion via index.css).
        shake: 'shake 0.45s ease-in-out both',
        'chevron-down': 'chevron-down 0.4s ease-in-out',
      },
    },
  },
  plugins: [],
}
