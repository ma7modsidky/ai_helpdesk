import { useEffect, useState } from 'react';

/**
 * Debounce a rapidly changing value, used for the inbox search box.
 *
 * Without it a five-letter query would be five requests, each with its own server round
 * trip, and the responses could arrive out of order (07 §9).
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
