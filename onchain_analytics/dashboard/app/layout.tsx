import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Navigation } from '@/components/Navigation';
import { LiveProviders } from '@/components/LiveProviders';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'ACU Token Analytics',
  description: 'Real-time analytics for ACU token on BSC',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
          <Navigation />
          <main className="container mx-auto px-4 py-6">
            {children}
          </main>
          <LiveProviders />
        </div>
      </body>
    </html>
  );
}
