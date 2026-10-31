import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

beforeEach(() => {
  // Locale and theme both persist to localStorage, so every test starts from the
  // same empty state instead of inheriting the previous test's choice.
  window.localStorage.clear();
  document.documentElement.removeAttribute('dir');
  document.documentElement.removeAttribute('lang');
  document.documentElement.removeAttribute('data-mui-color-scheme');
});

afterEach(() => {
  cleanup();
});
