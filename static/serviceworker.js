// Malita PWA service worker.
//
// This app is a live Streamlit experience driven over a WebSocket, not a
// static site, so we deliberately do NOT cache page responses here - doing
// so risks serving a stale UI on top of a live session and breaking things
// in ways that are hard to diagnose. This worker's only job is to satisfy
// the browser's PWA-installability requirement (a registered service
// worker with a fetch handler); every request is just passed straight
// through to the network.
self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
