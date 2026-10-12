import { Loader2 } from 'lucide-react';

/** Shown while a lazily-loaded page chunk is being fetched. */
export function PageFallback() {
  return (
    <div className="flex h-full min-h-[40vh] items-center justify-center" role="status" aria-label="Loading page">
      <Loader2 className="h-6 w-6 animate-spin text-accent-primary" aria-hidden="true" />
    </div>
  );
}
