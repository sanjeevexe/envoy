import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Envoy",
  description: "Envoy operates your phone apps for you and remembers what it sees.",
  // Phase 5: the iPhone companion is this app on the Home Screen (standalone, its own icon, push notifications).
  manifest: "/manifest.webmanifest",
  appleWebApp: { title: "Envoy", capable: true, statusBarStyle: "default" },
  icons: { icon: "/icons/favicon-64.png", apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#ffffff" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
