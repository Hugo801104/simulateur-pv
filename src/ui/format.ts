/** Mise en forme des nombres (convention française). */

const nf = (digits: number) => new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits, minimumFractionDigits: digits });

export function num(value: number | null | undefined, digits = 0): string {
  return value == null || !Number.isFinite(value) ? '—' : nf(digits).format(value);
}

export function kwh(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return Math.abs(value) >= 100_000 ? `${num(value / 1000, 1)} MWh` : `${num(value)} kWh`;
}

export function eur(value: number | null | undefined, digits = 0): string {
  return value == null || !Number.isFinite(value) ? '—' : `${nf(digits).format(value)} €`;
}

export function pct(ratio: number | null | undefined, digits = 0): string {
  return ratio == null || !Number.isFinite(ratio) ? '—' : `${nf(digits).format(ratio * 100)} %`;
}

export function years(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'non atteint';
  return `${num(value, 1)} ans`;
}

export const MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}
