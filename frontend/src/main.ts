import { createApp } from 'vue'
import { createI18n } from 'vue-i18n'
import { createPinia } from 'pinia'
import AOS from 'aos'
import 'aos/dist/aos.css'
import './style.css'
// PrimeVue imports
import PrimeVue from 'primevue/config'
import Lara from '@primeuix/themes/lara'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import 'primeicons/primeicons.css'

import App from './App.vue'
import router from './router'
import messages from './i18n'

// Initialize AOS
AOS.init({
	once: true,
	duration: 700,
	easing: 'ease-out-cubic'
})

const app = createApp(App)

// i18n
const i18n = createI18n({
	legacy: false,
	locale: 'pl',
	fallbackLocale: 'en',
	messages
})

// Pinia store
app.use(createPinia())

// Router
app.use(router)

// i18n
app.use(i18n)

// PrimeVue with Lara theme (Tailwind-friendly unstyled base)
app.use(PrimeVue, {
	theme: {
		preset: Lara,
		options: {
			darkModeSelector: '.dark'
		}
	},
	unstyled: false, // Można ustawić na true dla pełnej kontroli Tailwind
	pt: {} // Pass-through dla custom stylowania
})
app.use(ToastService)
app.use(ConfirmationService)

app.mount('#app')
