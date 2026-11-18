import { AlertCircle, ArrowUpRight, Inbox } from 'lucide-react';
import { Button } from './button';
import { cn } from '@/lib/utils';
export function Badge({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn('badge', className)}>{children}</span>;
}
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton', className)} aria-hidden="true" />;
}
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={24} />
      <strong>Something didn’t load</strong>
      <p>{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Inbox size={28} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function Trend({ children }: { children: React.ReactNode }) {
  return (
    <span className="trend">
      <ArrowUpRight size={12} />
      {children}
    </span>
  );
}
export function Dot({ color, className }: { color: string; className?: string }) {
  return <span className={cn('color-dot', className)} style={{ background: color }} />;
}
export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd>{children}</kbd>;
}
