import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "CELPIP Writing Coach",
  description: "AI-assisted CELPIP writing practice",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

