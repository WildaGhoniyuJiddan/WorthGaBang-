import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WorthGaBang — Cek Harga PC & Laptop",
  description: "Validasi harga produk dari pembanding marketplace nyata.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}

