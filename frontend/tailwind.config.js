/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#0a0c0f',
        bg2: '#111419',
        bg3: '#1a1f28',
        bg4: '#222836',
        border: 'rgba(255,255,255,0.07)',
        text: '#e8eaf0',
        text2: '#8b9ab0',
        text3: '#5a6880',
        accent: '#00d4aa',
        blue: '#0077ff',
        warn: '#ff9500',
        danger: '#ff3b5c',
        purple: '#a78bfa'
      },
      fontFamily: {
        sans: ['"Space Grotesk"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      }
    },
  },
  plugins: [],
}
