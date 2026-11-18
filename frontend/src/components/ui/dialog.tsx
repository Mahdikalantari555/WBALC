'use client';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;
export function DialogContent({
  children,
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="dialog-overlay" />
      <DialogPrimitive.Content className={cn('dialog-content', className)} {...props}>
        {children}
        <DialogPrimitive.Close className="dialog-close" aria-label="Close dialog">
          <X size={18} />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
export function DialogHeader({ children }: { children: React.ReactNode }) {
  return <div className="dialog-header">{children}</div>;
}
export function DialogTitle({ children }: { children: React.ReactNode }) {
  return <DialogPrimitive.Title className="dialog-title">{children}</DialogPrimitive.Title>;
}
export function DialogDescription({ children }: { children: React.ReactNode }) {
  return (
    <DialogPrimitive.Description className="dialog-description">
      {children}
    </DialogPrimitive.Description>
  );
}
