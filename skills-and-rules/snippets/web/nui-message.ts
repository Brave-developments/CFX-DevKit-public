// Browser event subscription. Remove listener during unmount.
export function onNuiMessage<T>(handler: (data: T) => void): () => void {
  const listener = (event: MessageEvent<T>) => handler(event.data);
  window.addEventListener('message', listener);
  return () => window.removeEventListener('message', listener);
}
