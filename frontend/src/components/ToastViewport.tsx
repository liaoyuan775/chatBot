import { useEffect, useMemo, useState } from "react";
import { subscribeToast, type ToastMessage } from "../store/toastBus";

const DURATION_MS = 2000;

export function ToastViewport() {
  const [items, setItems] = useState<ToastMessage[]>([]);

  useEffect(() => {
    return subscribeToast((toast) => {
      setItems((current) => [...current, toast]);
      window.setTimeout(() => {
        setItems((current) => current.filter((item) => item.id !== toast.id));
      }, DURATION_MS);
    });
  }, []);

  const visible = useMemo(() => items.slice(-3), [items]);
  if (!visible.length) return null;

  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {visible.map((toast) => (
        <div
          key={toast.id}
          className={`toast-item ${
            toast.kind === "success" ? "toast-item-success" : toast.kind === "error" ? "toast-item-error" : "toast-item-info"
          }`}
        >
          {toast.message}
        </div>
      ))}
    </div>
  );
}
