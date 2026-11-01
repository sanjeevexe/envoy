import type { Metadata, Viewport } from "next";
// Self-hosted fonts (no Google at run time: the static build and the iPhone app on the tailnet work offline):
// Fraunces for Envoy's voice, Manrope for everything else.
import "@fontsource-variable/fraunces/opsz.css";
import "@fontsource-variable/manrope";
import "./globals.css";

export const metadata: Metadata = {
  title: "Envoy",
  description: "Envoy operates your phone apps for you and remembers what it sees.",
  // Phase 5: the iPhone companion is this app on the Home Screen (standalone, its own icon, push notifications).
  manifest: "/manifest.webmanifest",
  appleWebApp: { title: "Envoy", capable: true, statusBarStyle: "default" },
  icons: { icon: [{ url: "/icons/favicon.svg", type: "image/svg+xml" }, { url: "/icons/favicon-64.png", sizes: "64x64" }], apple: "/icons/apple-touch-icon.png" },
};

// The page's own color, so the iOS status bar runs straight into the app's header (cream, or deep green in dark mode).
export const viewport: Viewport = {
  width: "device-width", initialScale: 1, viewportFit: "cover",
  themeColor: "#EFEBE2",  // light only for now (globals.css)
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
