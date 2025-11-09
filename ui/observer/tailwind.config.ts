import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#05060a',
        panel: '#0f1118',
        accent: '#4ade80',
        warning: '#fb923c',
        danger: '#f87171',
      },
    },
  },
  plugins: [],
} satisfies Config
