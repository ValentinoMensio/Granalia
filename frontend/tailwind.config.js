export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          red: '#c7391f',
          sand: '#efe1c8',
          ink: '#2f241b',
          gold: '#d9b354',
        },
      },
      boxShadow: {
        card: '0 20px 45px rgba(72, 48, 24, 0.10)',
      },
    },
  },
  plugins: [],
}
