/** Matches the gateway's FastAPI error envelope: `HTTPException(detail=...)` / the global 500 handler. */
export type GatewayErrorEnvelope = {
  detail: string | Record<string, unknown>;
};

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "REQUEST_FAILED");
    this.status = status;
    this.detail = detail;
  }
}
