import { useCallback, useState } from 'react';

import { errorMessageKey, isApiError } from '@/lib/api/errors';

/**
 * Turn an API failure into something a form can render.
 *
 * The contract's `400 validation_error` carries one message per field, so those land on
 * the matching control. Anything else becomes a form-level message keyed to the catalog
 * — never the raw server text, and never a stack trace (07 §2.5).
 */
export interface ApiFormErrors {
  readonly fieldErrors: Record<string, string>;
  readonly formError: string | null;
  readonly applyError: (error: unknown) => void;
  readonly reset: () => void;
}

export function useApiFormErrors(): ApiFormErrors {
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const applyError = useCallback((error: unknown) => {
    if (isApiError(error)) {
      const fields = error.fieldErrors();
      setFieldErrors(fields);
      if (Object.keys(fields).length > 0) {
        setFormError(null);
        return;
      }
    }
    setFieldErrors({});
    setFormError(errorMessageKey(error));
  }, []);

  const reset = useCallback(() => {
    setFieldErrors({});
    setFormError(null);
  }, []);

  return { fieldErrors, formError, applyError, reset };
}
