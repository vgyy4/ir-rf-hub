/** Parsing for hand-written raw timing lists.
 *
 * Shared by the recording wizard's "write raw" step and the edit wizard's
 * raw editor, which must accept exactly the same format: comma-separated
 * microseconds, positive = mark (on), negative = space (off) -- the format
 * the ESP records in and the backend transmits from.
 */

function parse(text: string): number[] | null {
  const parts = text
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  if (parts.length === 0) return null;
  const nums = parts.map(Number);
  if (nums.some((n) => !Number.isInteger(n))) return null;
  return nums;
}

/** Returns null if the text isn't a valid non-empty list of integers. */
export function parseTimingsText(text: string): number[] | null {
  return parse(text);
}

/** Same format, but empty text is valid and means "no repeat signal".
 * Returns `undefined` -- distinct from `null` -- when the text is non-empty
 * but malformed, so callers can tell "cleared" from "invalid". */
export function parseOptionalTimingsText(text: string): number[] | null | undefined {
  if (text.trim().length === 0) return null;
  return parse(text) ?? undefined;
}

export const TIMINGS_FORMAT_ERROR = "Raw timings must be a comma-separated list of integers";
