import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Empório da Música | Atendimento",
  description: "Atendimento virtual da Empório da Música.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
