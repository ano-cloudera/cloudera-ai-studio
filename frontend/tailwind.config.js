/** @type {import('tailwindcss').Config} */
export default {
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        cloudera: {
          orange: '#FF5A1F',
          navy: '#15084A',
          violet: '#635BFF',
          ink: '#18162A',
          mist: '#F7F8FC'
        }
      },
      boxShadow: {
        card: '0 1px 2px rgba(20, 8, 74, 0.04), 0 12px 34px rgba(20, 8, 74, 0.06)'
      }
    }
  },
  plugins: []
}
