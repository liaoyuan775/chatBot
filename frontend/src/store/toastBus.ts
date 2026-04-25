export type ToastKind = "success" | "error" | "info";

export type ToastMessage = {
  id: number;
  kind: ToastKind;
  message: string;
};

type Listener = (toast: ToastMessage) => void;

let sequence = 0;
const listeners = new Set<Listener>();

export function emitToast(message: string, kind: ToastKind = "info") {
  const text = message.trim();
  if (!text) return;
  const toast: ToastMessage = {
    id: ++sequence,
    kind,
    message: text
  };
  listeners.forEach((listener) => listener(toast));
}

export function subscribeToast(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
