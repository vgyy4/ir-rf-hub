import { describe, expect, it } from "vitest";
import { parseOptionalTimingsText, parseTimingsText } from "./timings";

describe("parseTimingsText", () => {
  it("parses a comma-separated list of signed integers", () => {
    expect(parseTimingsText("9000, -4500, 560, -560")).toEqual([9000, -4500, 560, -560]);
  });

  it("tolerates extra whitespace and trailing commas", () => {
    expect(parseTimingsText(" 100 ,  -200 ,")).toEqual([100, -200]);
  });

  it("rejects empty input", () => {
    expect(parseTimingsText("")).toBeNull();
    expect(parseTimingsText("   ")).toBeNull();
  });

  it("rejects non-integer values", () => {
    expect(parseTimingsText("100, 1.5, -200")).toBeNull();
    expect(parseTimingsText("100, abc, -200")).toBeNull();
  });
});

describe("parseOptionalTimingsText", () => {
  it("treats empty/whitespace-only text as explicitly cleared (null)", () => {
    expect(parseOptionalTimingsText("")).toBeNull();
    expect(parseOptionalTimingsText("   ")).toBeNull();
  });

  it("parses a valid non-empty list", () => {
    expect(parseOptionalTimingsText("100, -200")).toEqual([100, -200]);
  });

  it("returns undefined (not null) for malformed non-empty text", () => {
    // Distinct from "cleared" -- callers need to tell "the user typed
    // garbage" apart from "the user cleared the field".
    expect(parseOptionalTimingsText("not numbers")).toBeUndefined();
  });
});
