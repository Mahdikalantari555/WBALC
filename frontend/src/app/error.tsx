'use client';
import { useEffect } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main className="fatal-error">
      <span className="empty-icon">
        <AlertTriangle size={30} />
      </span>
      <h1>Let’s find our bearings.</h1>
      <p>
        Something unexpected interrupted your workspace. Your saved projects and labels are safe.
      </p>
      <Button onClick={reset}>
        <RefreshCw size={16} />
        Reload workspace
      </Button>
    </main>
  );
}
