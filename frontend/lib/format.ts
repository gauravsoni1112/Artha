/**
 * Formatting helpers for Artha.
 *
 * INVARIANT: All monetary values in the backend are PAISE (integer BigInt).
 * Never perform arithmetic in floats. Conversion to rupees happens only for
 * display, using integer arithmetic.
 *
 * formatINR(paise) mirrors the Python libs/schemas/money.py format_inr().
 */

/** Convert paise (int) to a display string like "₹1,23,456.78" */
export function formatINR(paise: number): string {
  if (!Number.isFinite(paise)) return "₹—";

  const negative = paise < 0;
  const absPaise = Math.abs(paise);

  // Integer and fractional parts — use integer arithmetic
  const rupees = Math.floor(absPaise / 100);
  const paiseRemainder = absPaise % 100;

  // Indian number format: last 3 digits, then groups of 2
  const rupeesStr = rupees.toString();
  let formatted: string;
  if (rupeesStr.length <= 3) {
    formatted = rupeesStr;
  } else {
    const tail = rupeesStr.slice(-3);
    const head = rupeesStr.slice(0, -3);
    const headFormatted = head.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    formatted = `${headFormatted},${tail}`;
  }

  const paiseStr = paiseRemainder.toString().padStart(2, "0");
  const result = `₹${formatted}.${paiseStr}`;
  return negative ? `-${result}` : result;
}

/** Short form: "₹1.2L", "₹45.3K", "₹1.2Cr" */
export function formatINRShort(paise: number): string {
  if (!Number.isFinite(paise)) return "₹—";
  const negative = paise < 0;
  const abs = Math.abs(paise);
  const rupees = abs / 100;

  let s: string;
  if (rupees >= 1_00_00_000) {
    s = `₹${(rupees / 1_00_00_000).toFixed(1)}Cr`;
  } else if (rupees >= 1_00_000) {
    s = `₹${(rupees / 1_00_000).toFixed(1)}L`;
  } else if (rupees >= 1_000) {
    s = `₹${(rupees / 1_000).toFixed(1)}K`;
  } else {
    s = `₹${rupees.toFixed(0)}`;
  }
  return negative ? `-${s}` : s;
}

/** Format a date string (ISO) as "15 Mar 2025" */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** Format a confidence score (0–1) as a percent string like "82%" */
export function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

/** Return a colour class for a confidence score */
export function confidenceColor(confidence: number): string {
  if (confidence >= 0.75) return "text-green-600 dark:text-green-400";
  if (confidence >= 0.5) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

/** Return a colour class for a goal progress % */
export function progressColor(pct: number): string {
  if (pct >= 75) return "bg-green-500";
  if (pct >= 40) return "bg-yellow-500";
  return "bg-red-500";
}
