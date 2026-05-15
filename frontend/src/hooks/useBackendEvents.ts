import { useEffect, useRef } from 'react';
import { eventsUrl } from '../api/client';

export type BackendEvent = {
  type: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
};

export function useBackendEvents(eventTypes: string[], callback: (event: BackendEvent) => Promise<void> | void, debounceMs = 250) {
  const callbackRef = useRef(callback);
  const typesKey = eventTypes.join('|');

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!window.EventSource) return undefined;

    const allowed = new Set(eventTypes);
    const source = new EventSource(eventsUrl());
    let timer: number | undefined;
    let latestEvent: BackendEvent | undefined;

    const schedule = (event: BackendEvent) => {
      if (document.visibilityState === 'hidden') return;
      latestEvent = event;
      if (timer !== undefined) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        timer = undefined;
        void callbackRef.current(latestEvent ?? event);
      }, debounceMs);
    };

    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as BackendEvent;
        if (event.type === 'connected') return;
        if (allowed.size === 0 || allowed.has(event.type)) schedule(event);
      } catch {
        // Ignore malformed event frames. The browser will keep the stream open.
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        schedule({ type: 'visibility.resumed' });
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      source.close();
    };
  }, [debounceMs, typesKey]);
}
