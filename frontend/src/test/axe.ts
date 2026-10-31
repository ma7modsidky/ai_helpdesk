import axe from 'axe-core';
import { expect } from 'vitest';

/**
 * Run axe-core against rendered markup and fail on any violation.
 *
 * jsdom cannot compute colour contrast, so the contrast claim is verified separately by
 * `src/theme/tokens.test.ts` against the token values; what this catches is the structural
 * half: missing labels, missing landmarks, bad heading order, invalid ARIA, and duplicate
 * ids. Both halves are needed for the accessibility claim to mean anything (07 §11).
 */
export async function expectNoAxeViolations(): Promise<void> {
  // The whole document, not the render container: MUI renders dialogs and menus into a
  // portal on `document.body`, and scanning only the container would silently skip the
  // most complex markup on the page.
  const results = await axe.run(document.body, {
    rules: {
      // Not evaluable without layout or a real renderer.
      'color-contrast': { enabled: false },
      region: { enabled: false },
    },
  });

  // Include the offending markup: a violation id alone sends the reader back to the
  // browser to find the element, which is exactly the work a failing gate should do.
  const summary = results.violations
    .map(
      (violation) =>
        `${violation.id}: ${violation.help}\n` +
        violation.nodes.map((node) => `  ${node.target.join(' ')}  ->  ${node.html}`).join('\n'),
    )
    .join('\n');

  expect(results.violations, summary).toHaveLength(0);
}
