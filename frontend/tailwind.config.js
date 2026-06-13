/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          bg: '#0a0a0d',
          surface: '#13131a',
          raised: '#191922',
          border: '#23232e',
          divider: '#1c1c26',
        },
        accent: {
          DEFAULT: '#5eead4',
          muted: '#2dd4bf',
          dim: 'rgba(94, 234, 212, 0.12)',
        },
        positive: '#34d399',
        negative: '#f87171',
        warn: '#fbbf24',
        muted: {
          DEFAULT: '#8b8b9a',
          dim: '#5c5c6b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': '0.6875rem',
      },
      borderRadius: {
        DEFAULT: '0.5rem',
      },
    },
  },
  plugins: [],
}

