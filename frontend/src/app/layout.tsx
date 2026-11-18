import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { Providers } from '@/components/providers';
import './globals.css';
export const metadata: Metadata = {
  title: 'TerraLab · Human insight. Earth intelligence.',
  description:
    'A research workspace for water-body monitoring with multi-temporal Sentinel imagery, native geospatial metadata, and reusable satellite analysis tools.',
};
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
