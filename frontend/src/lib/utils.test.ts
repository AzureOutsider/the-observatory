import { describe, expect, it } from "vitest";
import { sampleData } from "./utils";

describe("sampleData", () => {
  it("returns the original data when sampling is unnecessary", () => {
    const data = [1, 2, 3];

    expect(sampleData(data, 5)).toBe(data);
  });

  it("limits large series while preserving the first and last points", () => {
    const data = Array.from({ length: 20 }, (_, index) => index);

    const sampled = sampleData(data, 5);

    expect(sampled).toHaveLength(5);
    expect(sampled[0]).toBe(0);
    expect(sampled[sampled.length - 1]).toBe(19);
  });

  it("does not sample when the requested limit is too small", () => {
    const data = [1, 2, 3, 4];

    expect(sampleData(data, 2)).toBe(data);
  });
});
