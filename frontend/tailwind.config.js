export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          red: '#84261a',
          sand: '#e2d3bc',
          ink: '#1e1915',
          gold: '#af7f2d',
        },
      },
      boxShadow: {
        card: '0 18px 42px rgba(44, 31, 22, 0.13)',
      },
    },
  },
  plugins: [],
}
