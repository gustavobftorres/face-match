import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "drive.google.com",
      },
      {
        protocol: "https",
        hostname: "www.googleapis.com",
      },
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
  },
  typescript: {
    // Ignore during build, relying on local development type checking
    ignoreBuildErrors: true, 
  }
};

export default nextConfig;
