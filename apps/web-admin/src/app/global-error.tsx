"use client";

import { useEffect } from "react";

// Next.js only renders global-error.tsx when the ROOT layout itself throws,
// so it must render its own <html>/<body> -- it replaces the whole document,
// there is no ancestor layout left to provide them. Kept dependency-free
// (no lucide-react icons, no shared components) since a failure this deep
// may mean those modules themselves failed to load.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("Unhandled error in web-admin root layout:", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "2.5rem 1.5rem",
          background:
            "linear-gradient(180deg, #08101f 0%, #0f1730 52%, #08101b 100%)",
          color: "#f4f7fb",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: "32rem",
            borderRadius: "2rem",
            border: "1px solid rgba(158, 180, 214, 0.14)",
            background: "rgba(13, 20, 39, 0.88)",
            boxShadow: "0 18px 60px rgba(0, 0, 0, 0.25)",
            padding: "2rem",
            textAlign: "center",
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: "0.7rem",
              textTransform: "uppercase",
              letterSpacing: "0.3em",
              color: "#9aa8bd",
            }}
          >
            Critical error
          </p>
          <h1 style={{ marginTop: "0.75rem", fontSize: "1.5rem", fontWeight: 600 }}>
            SahulatKar Admin failed to load
          </h1>
          <p style={{ marginTop: "0.5rem", fontSize: "0.875rem", lineHeight: 1.6, color: "#9aa8bd" }}>
            A critical error prevented the admin console from rendering. Try reloading -- if this
            keeps happening, contact platform engineering.
          </p>
          {error.message && (
            <p
              style={{
                marginTop: "1rem",
                borderRadius: "0.75rem",
                border: "1px solid rgba(158, 180, 214, 0.14)",
                background: "rgba(2, 6, 15, 0.6)",
                padding: "0.75rem 1rem",
                textAlign: "left",
                fontFamily: "monospace",
                fontSize: "0.75rem",
                color: "#9aa8bd",
                wordBreak: "break-word",
              }}
            >
              {error.message}
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: "1.5rem",
              borderRadius: "9999px",
              border: "none",
              background: "#f5b301",
              color: "#0a1020",
              fontWeight: 600,
              fontSize: "0.875rem",
              padding: "0.65rem 1.5rem",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
