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
        ink: {
          950: '#04070D',
          900: '#060A12',
          850: '#090F1B',
          800: '#0C1424',
          700: '#131F38',
          600: '#1E2D4A',
        },
        text: {
          primary: '#E6EDF7',
          secondary: '#8FA3BF',
          muted: '#5F738F',
        },
        accent: {
          cyan: '#22D3EE',
          indigo: '#818CF8',
          violet: '#A78BFA',
          alert: '#FF3B5C',
        },
        severity: {
          teal: '#2DD4BF',
          yellow: '#FDE047',
          coral: '#FB7185',
        },
        engine: {
          milp: '#60A5FA',
          linucb: '#FB923C',
          proportional: '#4ADE80',
        },
      },
      fontFamily: {
        heading: ['"Space Grotesk"', 'sans-serif'],
        sans: ['Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      backdropBlur: {
        glass: '16px',
      },
      keyframes: {
        aurora: {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
        pulseAlert: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.4', transform: 'scale(0.98)' },
        },
        shockwave: {
          '0%': { transform: 'scale(0.8)', opacity: '1' },
          '100%': { transform: 'scale(2.2)', opacity: '0' },
        },
      },
      animation: {
        aurora: 'aurora 15s ease infinite',
        pulseAlert: 'pulseAlert 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        shockwave: 'shockwave 2s cubic-bezier(0, 0.2, 0.8, 1) infinite',
      },
    },
  },
  plugins: [],
}
