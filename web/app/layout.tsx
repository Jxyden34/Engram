import type { Metadata, Viewport } from "next";
import "./globals.css";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "Engram",
  description: "Self-hosted personal memory and AI context platform",
  applicationName: "Engram",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "Engram" },
  icons: { icon: [{ url: "/favicon.svg", type: "image/svg+xml" }], apple: "/apple-touch-icon.png" },
};

export const viewport: Viewport = { themeColor: "#090a0c" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head><meta name="apple-mobile-web-app-capable" content="yes" /></head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
