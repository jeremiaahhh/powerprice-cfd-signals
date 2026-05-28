/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    // Override default border radii — Bloomberg-terminal aesthetic is flat
    borderRadius: {
      none: '0',
      sm:   '1px',
      DEFAULT: '2px',
      md:   '2px',
      lg:   '2px',
      xl:   '2px',
      '2xl': '2px',
      '3xl': '2px',
      full: '9999px',  // keep full for status pills / dots
    },
    extend: {
      colors: {
        // Bloomberg-terminal palette
        term: {
          black: '#000000',
          bg: '#0a0a0a',          // application background
          panel: '#111111',       // cards / panels
          panel2: '#161616',      // raised / hover
          border: '#1f1f1f',      // dim borders
          'border-strong': '#2a2a2a',
        },
        amber: {
          DEFAULT: '#ffa500',     // signature amber
          dim: '#cc8400',
          bright: '#ffb84d',
        },
        bull: '#00ff66',          // bid / long / positive
        bear: '#ff3366',          // ask / short / negative
        warn: '#ffcc00',
        info: '#00d4ff',
        // Legacy hex colors still work — keep these aliases so existing pages render
        // until they are migrated:
        bg: { primary: '#000000', secondary: '#0a0a0a', card: '#111111', border: '#1f1f1f' },
        accent: { green: '#00ff66', red: '#ff3366', yellow: '#ffcc00', blue: '#00d4ff', purple: '#ffa500' },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', '14px'],
        '3xs': ['9px', '12px'],
      },
      textColor: {
        primary: '#e8e8e8',
        secondary: '#9a9a9a',
        muted: '#555555',
      },
    },
  },
  plugins: [],
}
