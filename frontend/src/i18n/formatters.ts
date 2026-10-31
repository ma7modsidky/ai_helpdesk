/**
 * One place for `Intl` formatting, so no component reaches for `toLocaleString`.
 *
 * Numerals stay Western Arabic (`latn`) in both locales by deliberate choice: it is
 * the convention in business software across the region and it keeps ticket numbers,
 * versions, and counts readable next to Latin identifiers (ADR-031).
 */

import { DEFAULT_LOCALE, type SupportedLocale } from './locale';

const INTL_TAGS: Record<SupportedLocale, string> = {
  en: 'en-u-nu-latn',
  ar: 'ar-u-nu-latn',
};

function intlTag(locale: SupportedLocale): string {
  return INTL_TAGS[locale] ?? INTL_TAGS[DEFAULT_LOCALE];
}

function toDate(value: string | number | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | number | Date, locale: SupportedLocale): string {
  const date = toDate(value);
  if (!date) {
    return '';
  }
  return new Intl.DateTimeFormat(intlTag(locale), { dateStyle: 'medium' }).format(date);
}

export function formatDateTime(value: string | number | Date, locale: SupportedLocale): string {
  const date = toDate(value);
  if (!date) {
    return '';
  }
  return new Intl.DateTimeFormat(intlTag(locale), {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function formatNumber(value: number, locale: SupportedLocale): string {
  return new Intl.NumberFormat(intlTag(locale)).format(value);
}

/** Largest unit first, so a difference is described by the coarsest unit that fits. */
type RelativeUnit = 'year' | 'month' | 'week' | 'day' | 'hour' | 'minute' | 'second';

const RELATIVE_UNITS: readonly RelativeUnit[] = [
  'year',
  'month',
  'week',
  'day',
  'hour',
  'minute',
  'second',
];

/**
 * "3 hours ago" / "قبل 3 ساعات", computed against an injectable `now` so the
 * boundary behaviour is testable rather than clock-dependent.
 */
export function formatRelativeTime(
  value: string | number | Date,
  locale: SupportedLocale,
  now: Date = new Date(),
): string {
  const date = toDate(value);
  if (!date) {
    return '';
  }
  const formatter = new Intl.RelativeTimeFormat(intlTag(locale), { numeric: 'auto' });
  const deltaSeconds = (date.getTime() - now.getTime()) / 1000;
  const deltas: Record<RelativeUnit, number> = {
    year: deltaSeconds / (60 * 60 * 24 * 365),
    month: deltaSeconds / (60 * 60 * 24 * 30),
    week: deltaSeconds / (60 * 60 * 24 * 7),
    day: deltaSeconds / (60 * 60 * 24),
    hour: deltaSeconds / (60 * 60),
    minute: deltaSeconds / 60,
    second: deltaSeconds,
  };
  for (const unit of RELATIVE_UNITS) {
    const amount = deltas[unit];
    if (Math.abs(amount) >= 1) {
      return formatter.format(Math.round(amount), unit);
    }
  }
  return formatter.format(0, 'second');
}
