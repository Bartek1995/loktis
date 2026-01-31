import tailwindcssPrimeUI from 'tailwindcss-primeui';

/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ['selector', '[class*="app-dark"]'],
    content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
    plugins: [tailwindcssPrimeUI],
    theme: {
        fontFamily: {
            sans: ['Poppins', 'system-ui', 'sans-serif'],
        },
        extend: {
            screens: {
                sm: '576px',
                md: '768px',
                lg: '992px',
                xl: '1200px',
                '2xl': '1920px'
            },
            backgroundImage: {
                'blue-gradient': 'linear-gradient(135deg, #468ef9 0%, #0c66ee 100%)',
                'header-gradient': 'linear-gradient(169.4deg, #3984f4 -6.01%, #0cd3ff 36.87%, #2f7cf0 78.04%, #0e65e8 103.77%)',
            },
            colors: {
                nefa: {
                    blue: '#0c66ee',
                    'blue-light': '#468ef9',
                    cyan: '#0cd3ff',
                }
            }
        }
    }
};
