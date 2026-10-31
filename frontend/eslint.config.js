import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import localRules from './eslint-rules/no-hardcoded-copy.js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['dist/**', 'coverage/**', 'node_modules/**', 'playwright-report/**'],
  },
  js.configs.recommended,
  // The type-checked rules need a program, which only the TypeScript configs provide.
  // Scoped to TS files, `eslint.config.js` itself stays lintable without a project.
  ...tseslint.configs.recommendedTypeChecked.map((config) => ({
    ...config,
    files: config.files ?? ['**/*.{ts,tsx}'],
  })),
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
      globals: {
        ...globals.browser,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      local: localRules,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // User-visible copy comes from the `en`/`ar` catalogs (T4.11, 07 §11).
      'local/no-hardcoded-copy': 'error',
      // Anything the API returns is untrusted text. Rich text is out of MVP scope,
      // so there is no path that needs raw HTML and no reason to allow it (07 §10).
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message:
            'dangerouslySetInnerHTML is banned: render API text as text, and sanitise through an allowlist if rich text is ever supported.',
        },
      ],
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    files: ['**/*.test.{ts,tsx}', 'vitest.setup.ts'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
    rules: {
      // A test asserts the copy it expects; routing that through `t()` would make the
      // assertion pass whatever the catalog said.
      'local/no-hardcoded-copy': 'off',
    },
  },
  {
    // Build scripts and the local lint rules run in Node, not the browser.
    files: ['scripts/**/*.mjs', 'eslint-rules/**/*.js'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
  prettier,
);
