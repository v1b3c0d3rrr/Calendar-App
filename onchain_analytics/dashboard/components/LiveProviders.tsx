'use client';

import { AlertToast } from './AlertToast';

/**
 * Client-side providers that need to run globally.
 * Mounted in the root layout.
 */
export function LiveProviders() {
  return <AlertToast />;
}
