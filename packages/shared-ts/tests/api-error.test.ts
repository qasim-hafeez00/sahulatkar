import { describe, expect, it } from "vitest";
import { ApiError } from "../src/api-error";

describe("ApiError", () => {
  it("uses the string detail as the error message", () => {
    const error = new ApiError(404, "ORDER_NOT_FOUND");
    expect(error.message).toBe("ORDER_NOT_FOUND");
    expect(error.status).toBe(404);
    expect(error.detail).toBe("ORDER_NOT_FOUND");
  });

  it("falls back to a generic message when detail is not a string", () => {
    const detail = { code: "VALIDATION_ERROR", fields: ["amount"] };
    const error = new ApiError(422, detail);
    expect(error.message).toBe("REQUEST_FAILED");
    expect(error.detail).toBe(detail);
  });

  it("is an instance of Error", () => {
    const error = new ApiError(500, "INTERNAL_SERVER_ERROR");
    expect(error).toBeInstanceOf(Error);
  });
});
