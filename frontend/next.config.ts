import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 通过 127.0.0.1 / localhost 访问时，Next.js 16 dev server 默认拦截
  // /_next/static 与 /_next/hmr 等 dev 资源（视为跨域），导致 React 无法 hydration、
  // HMR WebSocket 握手失败。显式放行本地访问来源。
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.9.57"],
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      // 前端启动时探测后端是否可达（lib/api.ts checkBackend）
      { source: "/health", destination: `${backend}/health` },
    ];
  },
};

export default nextConfig;
