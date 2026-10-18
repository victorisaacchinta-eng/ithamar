// Day-first date parsing for Indian statements. Output is ISO yyyy-mm-dd.

const MONTHS: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};
const NUMERIC = /^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})$/;
const NAMED = /^(\d{1,2})[\s\-/]?([A-Za-z]{3,9})[\s\-/,]*(\d{2}|\d{4})?$/;
const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

function year(y: string | undefined, def: number | null): number | null {
  if (y === undefined) return def;
  const n = parseInt(y, 10);
  return n < 100 ? 2000 + n : n;
}

function iso(y: number, m: number, d: number): string | null {
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function parseDate(text: string, defaultYear: number | null = null): string | null {
  const t = text.trim().replace(/,$/, "");
  let m = ISO.exec(t);
  if (m) return iso(+m[1], +m[2], +m[3]);
  m = NUMERIC.exec(t);
  if (m) {
    const y = year(m[3], defaultYear);
    return y ? iso(y, +m[2], +m[1]) : null;
  }
  m = NAMED.exec(t);
  if (m) {
    const mon = MONTHS[m[2].slice(0, 3).toLowerCase()];
    const y = year(m[3], defaultYear);
    if (mon && y) return iso(y, mon, +m[1]);
  }
  return null;
}
