// language.ts

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useLanguageStore = defineStore('language', () => {
  const selected = ref(localStorage.getItem('lang') || 'pl')

  function setLanguage(lang: string) {
    selected.value = lang
    localStorage.setItem('lang', lang)
  }

  return { selected, setLanguage }
})