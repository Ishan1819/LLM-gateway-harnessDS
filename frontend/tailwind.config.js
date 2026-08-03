/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        page: '#0f172a',
        card: '#1e293b',
        raised: '#243449',
        hairline: '#334155',
        axis: '#475569',

        // Ink
        ink: '#f1f5f9',
        'ink-secondary': '#cbd5e1',
        'ink-muted': '#94a3b8',

        // Status — always paired with an icon + label, never colour alone
        good: '#10b981',
        warning: '#f59e0b',
        critical: '#ef4444',

        // Categorical series palette. Validated against the #1e293b chart
        // surface: lightness band, chroma floor, CVD separation, normal-vision
        // floor and 3:1 contrast all pass. Assign in fixed order, never cycled.
        's1': '#3b82f6',
        's2': '#ea580c',
        's3': '#0d9488',
        's4': '#8b5cf6',
        's5': '#ec4899',
        's6': '#65a30d',
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Inter', 'sans-serif'],
      },
      borderRadius: {
        card: '14px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,0.30), 0 8px 24px -12px rgba(0,0,0,0.45)',
      },
    },
  },
  plugins: [],
}
