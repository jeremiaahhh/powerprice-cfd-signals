export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: { primary: '#0a0e1a', secondary: '#0f1629', card: '#141b2d', border: '#1e2d4a' },
        accent: { green: '#00d4aa', red: '#ff4757', yellow: '#ffa726', blue: '#2196f3', purple: '#9c27b0' }
      },
      fontFamily: { mono: ['JetBrains Mono', 'Fira Code', 'monospace'] },
      textColor: {
        primary: '#e8eaf0',
        secondary: '#8892b0',
        muted: '#4a5568'
      }
    }
  },
  plugins: []
}
