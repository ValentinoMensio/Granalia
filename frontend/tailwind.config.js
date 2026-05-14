export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          red: '#0B2545',
          sand: '#EEF2F7',
          ink: '#101828',
          gold: '#C77D36',
        },
      },
      boxShadow: {
        card: '0 18px 50px rgba(15, 23, 42, 0.10), inset 0 1px 0 rgba(255,255,255,0.88)'
      },
    },
  },
  plugins: [],
}
