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
        odin: {
          bg: '#050505',
          'bg-subtle': '#0A0A0A',
          'bg-elevated': '#0E0E11',
          surface: '#131316',
          'surface-hover': '#1B1B1E',
          'surface-active': '#222226',
          'surface-border': 'rgba(255, 255, 255, 0.08)',
          'surface-border-strong': 'rgba(255, 255, 255, 0.14)',
          
          // Brand Accent - Tactical Amber / Orange
          primary: '#FF7A00',
          'primary-hover': '#FF8A3D',
          'primary-glow': 'rgba(255, 122, 0, 0.22)',
          'primary-subtle': 'rgba(255, 122, 0, 0.10)',
          
          // HUD Tech Cyan / Secondary
          cyan: '#00D2FF',
          'cyan-subtle': 'rgba(0, 210, 255, 0.12)',

          // Status colors
          success: '#10B981',
          'success-subtle': 'rgba(16, 185, 129, 0.12)',
          warning: '#F59E0B',
          'warning-subtle': 'rgba(245, 158, 11, 0.12)',
          danger: '#EF4444',
          'danger-subtle': 'rgba(239, 68, 68, 0.12)',
          info: '#3B82F6',
          'info-subtle': 'rgba(59, 130, 246, 0.12)',

          // Typography
          text: '#F5F5F5',
          'text-muted': '#8E8E93',
          'text-dim': '#52525B',
          'text-dark': '#27272A',
        }
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      boxShadow: {
        'hud-glow': '0 0 20px -5px rgba(255, 122, 0, 0.25)',
        'cyan-glow': '0 0 20px -5px rgba(0, 210, 255, 0.25)',
        'danger-glow': '0 0 20px -5px rgba(239, 68, 68, 0.3)',
        'card-subtle': '0 4px 20px -2px rgba(0, 0, 0, 0.5)',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { opacity: '0.9', transform: 'scale(1)' },
          '50%': { opacity: '0.4', transform: 'scale(0.97)' },
        },
        radarScan: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        hudBlink: {
          '0%, 49%': { opacity: '1' },
          '50%, 100%': { opacity: '0' },
        }
      },
      animation: {
        'pulse-glow': 'pulseGlow 2.5s ease-in-out infinite',
        'radar-scan': 'radarScan 4s linear infinite',
        'hud-blink': 'hudBlink 1s infinite',
      }
    },
  },
  plugins: [],
}
