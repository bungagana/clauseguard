/** @type {import('next').NextConfig} */
const API_URL = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

const nextConfig = {
  // reading uploaded documents or a slow database round trip can take over the 30 s default of the rewrite proxy
  experimental: { proxyTimeout: 240000 },
  async rewrites() {
    // Proxies browser calls through this app's own origin to the ClauseGuard
    // backend, so the browser never makes a cross-origin request (the sandbox
    // API ships no CORS headers) and the API base can stay same-origin in the
    // client code.
    return [
      {
        source: "/api/cg/:path*",
        destination: `${API_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
