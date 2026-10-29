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

// Cream, like the app's own header, so the iOS status bar runs straight into it.
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#F6F3EC" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
