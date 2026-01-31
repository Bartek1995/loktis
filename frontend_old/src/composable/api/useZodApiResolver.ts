// /c:/Projects/PL-LOCAL-PLT_Intra_App/django_intraapp_template/global_vue_frontend/src/core/composables/api/useZodApiResolver.ts

import { reactive } from 'vue';
import { zodResolver } from '@primevue/forms/resolvers/zod';
import { z, type ZodType } from 'zod';
import type { FormResolverOptions } from '@primevue/forms';

/**
 * Typ funkcji resolvera, którego oczekuje komponent <Form> z PrimeVue.
 * @param options - Opcje przekazywane do resolvera.
 * @return - Obiekt z wynikami walidacji, który zawiera błędy dla pól formularza zwrócone przez backend.
 */
type PrimeVueResolver = (options: FormResolverOptions) => Promise<any>;

export function useZodApiResolver<S extends ZodType>(schema: S) {
  const apiErrors = reactive<Record<string, string>>({});
  const baseZodResolver = zodResolver(schema);

  const resolver: PrimeVueResolver = async (options) => {
    const zodResult = await baseZodResolver(options);

    if (zodResult && zodResult.errors) {
      for (const [field, msg] of Object.entries(apiErrors)) {
        zodResult.errors[field] = [{ message: msg }];
      }
    }

    return zodResult;
  };

  function setApiErrors(errors: Record<string, string | string[]>) {
    clearApiErrors();
    Object.entries(errors).forEach(([field, msgs]) => {
      apiErrors[field] = Array.isArray(msgs) ? msgs.join('; ') : msgs;
    });
  }

  function clearApiErrors() {
    Object.keys(apiErrors).forEach((k) => delete apiErrors[k]);
  }

  return { resolver, setApiErrors, clearApiErrors };
}