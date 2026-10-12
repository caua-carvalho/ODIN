/** @type {import('tailwindcss').Config} */
module.exports = {
  // NOTE: Update this to include the paths to all files that contain Nativewind classes.
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        canvas: '#050505',
        'surface-canvas': '#050505',
        'surface-base': '#0B0B0D',
        'surface-container': '#111113',
        'surface-elevated': '#171719',
        primary: '#F5F5F7',
        secondary: '#A1A1A6',
        muted: '#6E6E73',
        accent: '#FF7A00',
        'accent-secondary': '#FF9A3D',
        'accent-subtle': '#00D9FF',
        line: 'rgba(255, 255, 255, 0.06)',
        ok: '#34d399',
        err: '#f87171',
        warn: '#fbbf24',
      },
    },
  },
  plugins: [],
};