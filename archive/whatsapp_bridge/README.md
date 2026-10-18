# Archived WhatsApp Baileys Bridge

This folder contains the original Node.js Baileys WhatsApp multi-device bridge for the Chai Assistant.

## Contents
- `bridge.js`: Express/HTTP server + Baileys socket connection handling text, voice notes, PDFs, and automatic Bad MAC session recovery.
- `package.json` & `package-lock.json`: Dependencies (`@whiskeysockets/baileys`, `pino`, `qrcode`).

## How to Run (if ever needed):
1. `npm install`
2. `node bridge.js` (listening on port 5056 and communicating with Python orchestrator on port 5055).
