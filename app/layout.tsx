import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'XAU/USD Gold Intelligence',
  description: 'Live XAU/USD analysis, VCPR levels, macro context and broadcast dashboard.'
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
