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
          500: '#8b1a1a',
          600: '#7a1515',
          700: '#651010',
        },
        arcane: {
          500: '#4a3b8a',
          600: '#3d3080',
        },
      },
      fontFamily: {
        fantasy: ['"Cinzel"', 'serif'],
        body: ['"Inter"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
