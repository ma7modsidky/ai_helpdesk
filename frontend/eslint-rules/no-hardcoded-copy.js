/**
 * The no-hardcoded-copy rule (07 §11, T4.11).
 *
 * Every user-visible string has to come from the `en`/`ar` catalogs, and "review will
 * catch it" is how a catalog ends up 90% complete. Two things make copy user-visible:
 * JSX text, and the attributes that are read out or displayed as text — a literal
 * `aria-label` is as untranslatable as a literal heading.
 *
 * Deliberately narrow:
 * - Only string *literals*. `{t('…')}`, `{ticket.subject}`, and template expressions are
 *   already computed, and guessing whether their value is copy is not this rule's job.
 * - Text without a letter is allowed, so separators ("·", "—", "/") and numeric prefixes
 *   do not need a catalog entry.
 * - Test files are exempt: a test asserts the copy it expects, and routing that through
 *   `t()` would make the test pass whatever the catalog said.
 */

/** Attributes whose value is rendered as text or announced by assistive technology. */
const TEXT_ATTRIBUTES = new Set([
  'aria-description',
  'aria-label',
  'aria-placeholder',
  'aria-roledescription',
  'alt',
  'caption',
  'description',
  'heading',
  'helperText',
  'label',
  'placeholder',
  'subtitle',
  'title',
]);

const HAS_LETTER = /\p{L}/u;

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Require user-visible copy to come from the translation catalogs.',
    },
    schema: [],
    messages: {
      jsxText: 'Hardcoded copy in JSX. Pass the catalog key through `t(...)` instead (07 §11).',
      attribute:
        'Hardcoded copy in `{{name}}`. Pass the catalog key through `t(...)` instead (07 §11).',
    },
  },

  create(context) {
    return {
      JSXText(node) {
        if (HAS_LETTER.test(node.value)) {
          context.report({ node, messageId: 'jsxText' });
        }
      },

      JSXAttribute(node) {
        if (node.name.type !== 'JSXIdentifier' || !TEXT_ATTRIBUTES.has(node.name.name)) {
          return;
        }
        const value = node.value;
        if (value?.type === 'Literal' && typeof value.value === 'string') {
          if (HAS_LETTER.test(value.value)) {
            context.report({
              node: value,
              messageId: 'attribute',
              data: { name: node.name.name },
            });
          }
        }
      },
    };
  },
};

export default {
  meta: { name: 'local' },
  rules: { 'no-hardcoded-copy': rule },
};
