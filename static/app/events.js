const listeners = new Map();

export function on(eventName, handler) {
  const name = String(eventName || "");
  if (!name || typeof handler !== "function") return () => {};
  const handlers = listeners.get(name) || new Set();
  handlers.add(handler);
  listeners.set(name, handlers);
  return () => handlers.delete(handler);
}

export function emit(eventName, ...args) {
  const handlers = listeners.get(String(eventName || ""));
  if (!handlers) return;
  [...handlers].forEach((handler) => handler(...args));
}
