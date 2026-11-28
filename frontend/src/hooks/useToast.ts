import { toast as sonnerToast } from 'sonner';
import { announce } from '@/lib/accessibility';

/**
 * Enhanced toast hook with accessibility announcements
 */
export function useToast() {
  return {
    success: (message: string, description?: string) => {
      announce(message, 'polite');
      return sonnerToast.success(message, { description });
    },
    error: (message: string, description?: string) => {
      announce(`Error: ${message}`, 'assertive');
      return sonnerToast.error(message, { description });
    },
    info: (message: string, description?: string) => {
      announce(message, 'polite');
      return sonnerToast.info(message, { description });
    },
    warning: (message: string, description?: string) => {
      announce(`Warning: ${message}`, 'polite');
      return sonnerToast.warning(message, { description });
    },
    loading: (message: string) => {
      return sonnerToast.loading(message);
    },
    promise: <T,>(
      promise: Promise<T>,
      {
        loading,
        success,
        error,
      }: {
        loading: string;
        success: string | ((data: T) => string);
        error: string | ((error: any) => string);
      }
    ) => {
      return sonnerToast.promise(promise, { loading, success, error });
    },
  };
}
