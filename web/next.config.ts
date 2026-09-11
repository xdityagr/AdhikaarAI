import type { NextConfig } from "next";

/**
 * The FastAPI engine (eligibility, routing, corpus) runs separately on :8001.
 * Rewriting /api/* onto it means the browser only ever talks to one origin, so
 * there is no CORS layer to configure and no preflight on every call.
 */
const API_ORIGIN = process.env.ADHIKAAR_API_ORIGIN ?? "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
      // Rendered maps are served by the engine, and the chat's map card points
      // at them by path. Without this they 404 through the front end.
      { source: "/media/:path*", destination: `${API_ORIGIN}/media/:path*` },
    ];
  },

  // Chrome on this machine cannot reach the loopback interface (Windows
  // AppContainer network isolation), so the dev server is browsed over the
  // LAN address instead. Next treats that as a cross-origin dev request unless
  // it is named here.
  allowedDevOrigins: ["127.0.0.1", "localhost", "10.37.31.96", "172.25.128.1"],
};

export default nextConfig;
