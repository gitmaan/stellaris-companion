/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './pages/**/*.{js,ts,jsx,tsx}',
    './hooks/**/*.{js,ts,jsx,tsx}',
    './*.tsx',
  ],
  theme: {
    extend: {
      colors: {
        // Background layers - Deep space with subtle blue undertones
        bg: {
          primary: '#05080d',      // Darker, more cosmic
          secondary: '#0c1219',    // Subtle blue undertone
          tertiary: '#141c28',     // Panel backgrounds
          elevated: '#1a2535',     // Hover states, elevated surfaces
          glass: 'rgba(12, 18, 25, 0.7)', // Glassy background
          'glass-dark': 'rgba(5, 8, 13, 0.85)', // Darker glassy background
        },
        // Text colors - Crisp with cyan influence
        text: {
          primary: '#e8f4f8',      // Slightly cyan-tinted white
          secondary: '#7a8c99',    // Muted cyan-gray
          accent: '#4fd1c5',       // Stellaris teal
          muted: '#4a5568',        // Very muted
          dim: 'rgba(232, 244, 248, 0.5)', // Dimmed text
        },
        // Stellaris accent palette - Energy and power
        accent: {
          cyan: '#00d4ff',         // Primary energy color
          'cyan-dim': '#00a8cc',   // Dimmed cyan
          'cyan-glow': 'rgba(0, 212, 255, 0.4)',
          teal: '#4fd1c5',         // Secondary accent
          'teal-dim': '#38b2ac',
          green: '#48bb78',        // Success/positive
          yellow: '#ecc94b',       // Warning/attention
          'yellow-dim': '#d69e2e',
          orange: '#ed8936',       // Alert
          red: '#fc8181',          // Error/danger
          'red-dim': '#f56565',
          purple: '#9f7aea',       // Special/rare
          blue: '#4299e1',         // Info/neutral accent
        },
        // Border colors - Subtle energy lines
        border: {
          DEFAULT: '#1e3a5f',      // Deep blue border
          subtle: '#162a45',       // Very subtle
          glow: '#00d4ff',         // Energy glow color
          active: '#4fd1c5',       // Active state
          glass: 'rgba(255, 255, 255, 0.1)', // Glass border
        },
        // Discord brand
        discord: {
          DEFAULT: '#5865F2',
          hover: '#4752C4',
        },
      },
      fontFamily: {
        sans: ['Rajdhani', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Consolas', 'Liberation Mono', 'Menlo', 'monospace'],
        display: ['Orbitron', 'Rajdhani', 'sans-serif'], // Sci-fi display font for headers
      },
      fontSize: {
        'xs': '0.75rem',
        'sm': '0.875rem',
        'base': '1rem',
        'lg': '1.125rem',
        'xl': '1.25rem',
        '2xl': '1.5rem',
        '3xl': '1.875rem',
        'tiny': '0.65rem', // For technical labels
      },
      letterSpacing: {
        tighter: '-0.05em',
        tight: '-0.025em',
        normal: '0em',
        wide: '0.025em',
        wider: '0.05em',
        widest: '0.1em',
        'tech': '0.2em', // Wide spacing for tech headers
      },
      boxShadow: {
        'glow-sm': '0 0 10px rgba(0, 212, 255, 0.3)',
        'glow': '0 0 20px rgba(0, 212, 255, 0.4)',
        'glow-lg': '0 0 30px rgba(0, 212, 255, 0.5)',
        'glow-teal': '0 0 20px rgba(79, 209, 197, 0.4)',
        'inner-glow': 'inset 0 0 20px rgba(0, 212, 255, 0.1)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
      },
      backgroundImage: {
        // Cosmic gradients
        'cosmic-radial': 'radial-gradient(ellipse at center, #0c1219 0%, #05080d 70%)',
        'cosmic-subtle': 'radial-gradient(ellipse at 50% 0%, rgba(0, 212, 255, 0.03) 0%, transparent 50%)',
        'panel-gradient': 'linear-gradient(180deg, rgba(0, 212, 255, 0.05) 0%, transparent 100%)',
        'energy-line': 'linear-gradient(90deg, transparent, rgba(0, 212, 255, 0.5), transparent)',
        'scanline': 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 212, 255, 0.03) 2px, rgba(0, 212, 255, 0.03) 4px)',
        'grid-pattern': 'linear-gradient(rgba(0, 212, 255, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.05) 1px, transparent 1px)',
      },
      backgroundSize: {
        'grid': '40px 40px',
      },
      animation: {
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'pulse-glow': 'pulse-glow 4s ease-in-out infinite',
        'bounce-dots': 'bounce 1.4s infinite ease-in-out both',
        'spin-slow': 'spin 2s linear infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'highlight-flash': 'highlight-flash 2s ease-out',
        'energy-flow': 'energy-flow 3s linear infinite',
        'star-twinkle': 'star-twinkle 4s ease-in-out infinite',
        'data-stream': 'data-stream 1.5s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 10px rgba(0, 212, 255, 0.2)' },
          '50%': { boxShadow: '0 0 20px rgba(0, 212, 255, 0.4)' },
        },
        'highlight-flash': {
          '0%': {
            boxShadow: '0 0 0 2px #00d4ff, 0 0 20px rgba(0, 212, 255, 0.4)',
            background: 'linear-gradient(135deg, #0c1219 0%, rgba(0, 212, 255, 0.1) 100%)',
          },
          '100%': {
            boxShadow: 'none',
            background: '#0c1219',
          },
        },
        'energy-flow': {
          '0%': { backgroundPosition: '200% center' },
          '100%': { backgroundPosition: '-200% center' },
        },
        'star-twinkle': {
          '0%, 100%': { opacity: '0.3' },
          '50%': { opacity: '1' },
        },
        'data-stream': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
      },
      borderRadius: {
        'sm': '2px', // Sharper corners for tech look
        'DEFAULT': '4px',
        'md': '6px',
        'lg': '8px',
        'xl': '12px',
      },
    },
  },
  plugins: [],
}
