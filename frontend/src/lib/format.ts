// Locale and time zone are fixed so server and client render identical strings.
const LOCALE = "en-US";

const currency = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const currencyPrecise = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "USD" });
const currencyCompact = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});
const integer = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 1 });

export const formatCurrency = (value: number) => currency.format(value);
export const formatCurrencyPrecise = (value: number) => currencyPrecise.format(value);
export const formatCurrencyCompact = (value: number) => currencyCompact.format(value);
export const formatInteger = (value: number) => integer.format(Math.round(value));
export const formatCompact = (value: number) => compact.format(value);
export const formatPercent = (ratio: number) => percent.format(ratio);

/** Dataset dates are plain YYYY-MM-DD values; format them in UTC so they never shift a day. */
function toUtcDate(isoDate: string): Date {
  return new Date(`${isoDate}T00:00:00Z`);
}

const shortDate = new Intl.DateTimeFormat(LOCALE, { month: "short", day: "numeric", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat(LOCALE, { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const weekdayDate = new Intl.DateTimeFormat(LOCALE, {
  weekday: "short",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

export const formatShortDate = (isoDate: string) => shortDate.format(toUtcDate(isoDate));
export const formatLongDate = (isoDate: string) => longDate.format(toUtcDate(isoDate));
export const formatWeekdayDate = (isoDate: string) => weekdayDate.format(toUtcDate(isoDate));

export function formatDateRange(startIso: string, endIso: string): string {
  return `${formatShortDate(startIso)} – ${formatLongDate(endIso)}`;
}

/** The YYYY-MM-DD date `days` days after (or before, if negative) `isoDate`. */
export function shiftDate(isoDate: string, days: number): string {
  const date = toUtcDate(isoDate);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** Whole days from `fromIso` to `toIso` (positive when `toIso` is later). */
export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((toUtcDate(toIso).getTime() - toUtcDate(fromIso).getTime()) / 86_400_000);
}

/** "Store 001" from "STR-001". */
export function formatStore(storeId: string): string {
  return storeId.replace(/^STR-/, "Store ");
}
