const apiTarget = process.env.BACKEND_API_URL || 'http://127.0.0.1:8001'

/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: process.cwd(),
  // Dev overlay "1 Issue" when opening http://127.0.0.1:3001 while next dev binds 0.0.0.0
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  async rewrites() {
    return [
      // v1 management API (mounted at /api/v1 on backend)
      { source: '/api/v1/:path*', destination: `${apiTarget}/api/v1/:path*` },
      // Legacy Ask Data / platform routes (mounted at backend root)
      { source: '/api/chat/:path*', destination: `${apiTarget}/chat/:path*` },
      { source: '/api/usage/:path*', destination: `${apiTarget}/usage/:path*` },
      { source: '/api/models', destination: `${apiTarget}/models` },
      { source: '/api/random-queries', destination: `${apiTarget}/random-queries` },
      { source: '/api/health/ready', destination: `${apiTarget}/health/ready` },
      { source: '/api/health', destination: `${apiTarget}/health` },
      { source: '/api/version', destination: `${apiTarget}/version` },
    ]
  },
}

export default nextConfig
