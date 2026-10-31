import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, formatNumber, formatRelativeTime } from './formatters';

const INSTANT = '2026-03-04T09:30:00Z';

describe('date and time formatting', () => {
  it('renders the same instant differently per locale', () => {
    const english = formatDate(INSTANT, 'en');
    const arabic = formatDate(INSTANT, 'ar');

    expect(english).not.toBe(arabic);
    expect(english.length).toBeGreaterThan(0);
    expect(arabic.length).toBeGreaterThan(0);
  });

  it('keeps numerals Latin in both locales', () => {
    // Arabic-Indic digits would break scanning next to Latin identifiers such as slugs,
    // versions, and email addresses (ADR-031).
    expect(formatDate(INSTANT, 'ar')).toMatch(/2026/);
    expect(formatDate(INSTANT, 'en')).toMatch(/2026/);
  });

  it('returns an empty string for an unparseable value rather than "Invalid Date"', () => {
    expect(formatDate('not-a-date', 'en')).toBe('');
    expect(formatDateTime('nonsense', 'ar')).toBe('');
    expect(formatRelativeTime('nonsense', 'en')).toBe('');
  });

  it('includes a time component in the date-time format', () => {
    expect(formatDateTime(INSTANT, 'en').length).toBeGreaterThan(formatDate(INSTANT, 'en').length);
  });
});

describe('formatNumber', () => {
  it('groups digits with the locale separators and Latin numerals', () => {
    expect(formatNumber(1234, 'en')).toBe('1,234');
    expect(formatNumber(1234, 'ar')).toMatch(/1.?234/);
  });
});

describe('formatRelativeTime', () => {
  const now = new Date('2026-03-04T12:00:00Z');

  it('describes a past instant relative to now', () => {
    expect(formatRelativeTime('2026-03-04T09:00:00Z', 'en', now)).toMatch(/3 hours/);
    expect(formatRelativeTime('2026-03-04T09:00:00Z', 'ar', now)).not.toBe('');
  });

  it('walks up to the largest whole unit', () => {
    expect(formatRelativeTime('2026-03-01T12:00:00Z', 'en', now)).toMatch(/3 days/);
    // 28 days is under a whole month, so the week unit is the coarsest one that fits.
    expect(formatRelativeTime('2026-02-04T12:00:00Z', 'en', now)).toMatch(/4 weeks/);
  });

  it('describes a difference of a month or more in months', () => {
    expect(formatRelativeTime('2025-12-01T12:00:00Z', 'en', now)).toMatch(/3 months/);
    expect(formatRelativeTime('2024-03-04T12:00:00Z', 'en', now)).toMatch(/2 years/);
  });

  it('falls back to "now" for a difference under a second', () => {
    expect(formatRelativeTime(now, 'en', now)).toMatch(/now|second/i);
  });
});
