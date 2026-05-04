export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          red: '#1e407c',
          sand: '#ebedf3',
          ink: '#0f172a',
          gold: '#1e407c',
        },
      },
      boxShadow: {
        card: '0 1px 3px rgba(15, 23, 42, 0.08), 0 1px 2px rgba(15, 23, 42, 0.04)'
      },
    },
  },
  plugins: [],
}
