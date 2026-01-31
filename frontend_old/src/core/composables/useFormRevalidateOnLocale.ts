// useFormRevalidateOnLocale.ts

import { watch, nextTick } from 'vue';
import { useI18n } from "vue-i18n";
import { useLanguageStore } from '@/stores/language';
import type { FormInstance } from '@primevue/forms';
import type { Ref } from 'vue';

// Używamy bardziej precyzyjnego typu dla refa
export function useFormRevalidateOnLocale(formRef: Ref<FormInstance | null>) {
  const languageStore = useLanguageStore();
  const { locale } = useI18n();

  watch(
    () => languageStore.selected,
    (newLocale) => {
      if (newLocale) {
        locale.value = newLocale;
      }
    },
    { immediate: true }
  );

  watch(locale, async () => {
    await nextTick();
    
    if (formRef.value) {
      formRef.value.validate();
    }
  });
}