import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/chai/:path*",
        destination: "http://127.0.0.1:5055/api/:path*",
      },
    ];
  },
};

export default nextConfig;
