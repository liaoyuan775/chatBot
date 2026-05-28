function describeMicUnavailableReason() {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return "Microphone is not available in this environment.";
  }
  if (!window.isSecureContext) {
    const host = window.location?.host || "current host";
    return `Microphone access requires HTTPS or localhost. Current host: ${host}.`;
  }
  if (!navigator.mediaDevices) {
    return "navigator.mediaDevices is unavailable in this browser.";
  }
  if (!navigator.mediaDevices.getUserMedia) {
    return "getUserMedia is unavailable in this browser.";
  }
  return null;
}

export function ensureMicAccess() {
  const reason = describeMicUnavailableReason();
  if (reason) {
    throw new Error(reason);
  }
}

export function getMicSupportError() {
  return describeMicUnavailableReason();
}
