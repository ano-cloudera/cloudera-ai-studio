/** @type {import('tailwindcss').Config} */
export default {
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        // Cloudera brand colours (the brand palette): orange for the call to action and the one highlight, deep indigo for
        // hero and dark sections, electric indigo for data and secondary accents, dark navy for headings and text.
        cloudera: {
          orange: '#FF5A14',
          navy: '#13003D',
          violet: '#5351F6',
          indigo: '#5351F6',
          ink: '#17113F',
          mist: '#F6F7F9',
          blue: '#3779D6',
          border: '#E2E6ED'
        }
      },
      boxShadow: {
        card: '0 1px 2px rgba(20, 8, 74, 0.04), 0 12px 34px rgba(20, 8, 74, 0.06)'
      }
    }
  },
  plugins: []
}
