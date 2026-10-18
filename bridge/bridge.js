import makeWASocket, {
    useMultiFileAuthState,
    DisconnectReason,
    downloadMediaMessage,
    fetchLatestBaileysVersion,
    Browsers,
    makeCacheableSignalKeyStore
} from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';
import qrcodeImage from 'qrcode';
import pino from 'pino';
import fs from 'fs';
import path from 'path';
import http from 'http';
import crypto from 'crypto';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const AUTH_DIR = path.join(__dirname, 'auth_info_baileys');
const DATA_DIR = path.join(__dirname, '..', 'data');
const AUDIO_DIR = path.join(DATA_DIR, 'audio_temp');
const QR_FILE = path.join(DATA_DIR, 'qr.txt');
const QR_IMAGE_FILE = path.join(DATA_DIR, 'qr.png');

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(AUDIO_DIR)) fs.mkdirSync(AUDIO_DIR, { recursive: true });

const PYTHON_WEBHOOK_URL = process.env.PYTHON_WEBHOOK_URL || 'http://127.0.0.1:5055/webhook';
const BRIDGE_PORT = parseInt(process.env.BRIDGE_PORT || '5056', 10);

// Suppress verbose libsignal internal crypto session logs that clutter the terminal
const originalConsoleInfo = console.info;
console.info = function (...args) {
    if (typeof args[0] === 'string' && (
        args[0].startsWith('Closing session') ||
        args[0].startsWith('Removing old closed session') ||
        args[0].startsWith('Opening session')
    )) {
        return;
    }
    originalConsoleInfo.apply(console, args);
};

const originalConsoleWarn = console.warn;
console.warn = function (...args) {
    if (typeof args[0] === 'string' && (
        args[0].startsWith('Decrypted message with closed session') ||
        args[0].startsWith('Closing open session in favor of incoming prekey bundle') ||
        args[0].startsWith('Session already closed')
    )) {
        return;
    }
    originalConsoleWarn.apply(console, args);
};

let sock = null;
let connectionStatus = 'initializing';
let myJid = null;
const botSentMessageIds = new Set();
const STORE_FILE = path.join(DATA_DIR, 'message_store.json');
const messageStore = new Map();

// Load cached messages from store on startup
if (fs.existsSync(STORE_FILE)) {
    try {
        const raw = JSON.parse(fs.readFileSync(STORE_FILE, 'utf-8'));
        for (const [k, v] of raw) {
            messageStore.set(k, v);
        }
        console.log(`[Bridge] Loaded ${messageStore.size} cached messages from store.`);
    } catch (e) {}
}

function saveStore() {
    try {
        const arr = Array.from(messageStore.entries()).slice(-1000);
        fs.writeFileSync(STORE_FILE, JSON.stringify(arr), 'utf-8');
    } catch (e) {}
}
setInterval(saveStore, 10000);

// Clean up old sent message IDs periodically
setInterval(() => {
    if (botSentMessageIds.size > 1000) {
        botSentMessageIds.clear();
    }
}, 60000);

async function notifyPython(payload) {
    try {
        const data = JSON.stringify(payload);
        const url = new URL(PYTHON_WEBHOOK_URL);
        const req = http.request({
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(data)
            },
            timeout: 5000
        }, (res) => {
            // Response received from Python
        });
        req.on('error', (e) => {
            // Python core might not be listening yet, which is normal on startup
        });
        req.write(data);
        req.end();
    } catch (err) {
        console.error('[Bridge] Error notifying Python:', err.message);
    }
}

async function startSock() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();
    const pairingNumber = process.env.PAIRING_NUMBER ? process.env.PAIRING_NUMBER.replace(/[^0-9]/g, '') : null;
    const logger = pino({ level: 'warn' });

    sock = makeWASocket({
        version,
        logger,
        auth: {
            creds: state.creds,
            keys: makeCacheableSignalKeyStore(state.keys, logger)
        },
        // macOS/Safari fingerprint is closer to what WhatsApp expects from a companion
        // device, reducing aggressive session resets that cause iPhone decryption failures.
        browser: Browsers.macOS('Safari'),
        syncFullHistory: false,
        markOnlineOnConnect: true,
        fireInitQueries: true,
        printQRInTerminal: false,
        generateHighQualityLinkPreview: false,
        emitOwnEvents: false,
        getMessage: async (key) => {
            // Must return proto.IMessage (the .message field), not the full WAMessage.
            // WhatsApp server calls this during retry/re-delivery requests.
            const stored = messageStore.get(key.id);
            if (stored) {
                if (stored.message) return stored.message;
                return stored;
            }
            return undefined;
        }
    });

    if (pairingNumber && !sock.authState.creds.registered) {
        setTimeout(async () => {
            try {
                let code = await sock.requestPairingCode(pairingNumber);
                code = code?.match(/.{1,4}/g)?.join("-") || code;
                console.log('\n======================================================');
                console.log(`📲 WHATSAPP PAIRING CODE: ${code}`);
                console.log(`Open WhatsApp -> Linked Devices -> Link with phone number instead`);
                console.log('======================================================\n');
            } catch (err) {
                console.error('[Bridge] Failed to request pairing code:', err.message);
            }
        }, 3000);
    }

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            connectionStatus = 'qr_ready';
            fs.writeFileSync(QR_FILE, qr, 'utf-8');
            try {
                await qrcodeImage.toFile(QR_IMAGE_FILE, qr, { width: 350 });
            } catch (e) {
                console.error('[Bridge] Failed to write QR image:', e.message);
            }
            console.log('\n======================================================');
            console.log('SCAN THIS QR CODE IN WHATSAPP (Linked Devices):');
            console.log('======================================================\n');
            qrcode.generate(qr, { small: true });
            console.log('\n======================================================\n');
            await notifyPython({ event: 'qr_ready', qr });
        }

        if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            connectionStatus = 'disconnected';
            console.log(`[Bridge] Connection closed (${statusCode}). Reconnecting: ${shouldReconnect}`);
            if (shouldReconnect) {
                setTimeout(startSock, 3000);
            }
        } else if (connection === 'open') {
            connectionStatus = 'connected';
            myJid = sock.user.id.split(':')[0] + '@s.whatsapp.net';
            if (fs.existsSync(QR_FILE)) fs.unlinkSync(QR_FILE);
            if (fs.existsSync(QR_IMAGE_FILE)) fs.unlinkSync(QR_IMAGE_FILE);
            console.log(`\n✅ [Bridge] WhatsApp Connected Successfully! Logged in as: ${myJid}`);
            await notifyPython({ event: 'connected', myJid });
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // Handle messaging history set — this event fires on initial connection and after
    // key-distribution syncs. Acknowledging it ensures the iPhone (primary device)
    // registers our companion device's sender keys properly.
    sock.ev.on('messaging-history.set', ({ messages, contacts, chats, isLatest }) => {
        if (isLatest) {
            console.log(`[Bridge] Messaging history sync complete (${messages.length} messages).`);
        }
        // Cache any messages we receive during history sync
        for (const msg of messages) {
            if (msg.key?.id && msg.message) {
                messageStore.set(msg.key.id, msg.message);
            }
        }
    });

    // Handle sender-key distribution messages (group/self chat key refreshes).
    // These must NOT be forwarded to Python — they are internal Signal Protocol packets.
    sock.ev.on('messages.update', (updates) => {
        for (const update of updates) {
            if (update.key?.id && update.update?.message) {
                messageStore.set(update.key.id, update.update.message);
            }
        }
    });

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        // 'notify' = new real-time message pushed to device
        // 'append' = offline catchup message from primary device delivered to companion
        if (type !== 'notify' && type !== 'append') return;

        for (const msg of (messages || [])) {
            try {
                const msgId = msg.key?.id;
                const senderJid = msg.key?.remoteJid;
                const isFromMe = msg.key?.fromMe;

                // 1. Immediately drop any message sent by the bot (by ID prefix or set lookup)
                if (msgId && (msgId.startsWith('BOT_') || botSentMessageIds.has(msgId))) {
                    continue;
                }

                console.log(`[Bridge] UPSERT: type=${type} id=${msgId} fromMe=${isFromMe} jid=${senderJid} hasMessage=${!!msg.message} stub=${msg.messageStubType || 'none'}`);

                if (msg.messageStubType) {
                    console.warn(`[Bridge] Message stub: type=${msg.messageStubType} params=${JSON.stringify(msg.messageStubParameters)}`);
                }

                if (!msg.message) continue;

                // Cache incoming message for retries
                if (msgId && msg.message) {
                    messageStore.set(msgId, msg.message);
                    if (messageStore.size > 2000) {
                        const firstKey = messageStore.keys().next().value;
                        messageStore.delete(firstKey);
                    }
                }

                // Exclude status broadcasts
                if (senderJid === 'status@broadcast') continue;

                const myPhone = myJid ? myJid.split('@')[0] : null;
                const myLid = sock.user?.lid ? sock.user.lid.split('@')[0].split(':')[0] : null;

                // Allow messages where remoteJid belongs to our own number or LID (Note to Self).
                // Primary device (iPhone) or companion devices (Mac) sending to Note to Self.
                const isOurNumber = (myPhone && (
                    senderJid === myJid ||
                    senderJid.startsWith(myPhone) ||
                    senderJid.split('@')[0] === myPhone
                )) || (myLid && (
                    senderJid.startsWith(myLid) ||
                    senderJid.split('@')[0] === myLid
                ));

                if (!isOurNumber) {
                    console.log(`[Bridge] Ignored (not our number/LID): senderJid=${senderJid} myPhone=${myPhone} myLid=${myLid}`);
                    continue;
                }

                const messageType = Object.keys(msg.message)[0];
                let textContent = '';
                let audioFilePath = null;

                if (messageType === 'conversation') {
                    textContent = msg.message.conversation;
                } else if (messageType === 'extendedTextMessage') {
                    textContent = msg.message.extendedTextMessage?.text || '';
                } else if (messageType === 'audioMessage') {
                    // Voice note (.ogg Opus)
                    const buffer = await downloadMediaMessage(
                        msg,
                        'buffer',
                        {},
                        { logger: pino({ level: 'silent' }) }
                    );
                    const fileName = `voice_${Date.now()}_${msgId}.ogg`;
                    audioFilePath = path.join(AUDIO_DIR, fileName);
                    fs.writeFileSync(audioFilePath, buffer);
                    console.log(`[Bridge] Downloaded voice note to: ${audioFilePath}`);
                } else {
                    // Other message types (image caption, etc.)
                    textContent = msg.message[messageType]?.caption || '';
                }

                const trimmedText = textContent ? textContent.trim() : '';
                if (!trimmedText && !audioFilePath) continue;

                // 2. Extra guard: ignore if text matches known bot prefixes
                if (trimmedText && (
                    trimmedText.startsWith('🤖') ||
                    trimmedText.startsWith('⏳') ||
                    trimmedText.startsWith('⚠️') ||
                    trimmedText.startsWith('🎙️') ||
                    trimmedText.startsWith('🗣️') ||
                    trimmedText.startsWith('✍️') ||
                    trimmedText.startsWith('📁')
                )) {
                    continue;
                }

                console.log(`[Bridge] MSG => fromMe=${isFromMe} senderJid=${senderJid} type=${messageType} text="${trimmedText.substring(0, 50)}"`);

                const effectiveSender = (senderJid && !senderJid.endsWith('@lid')) ? senderJid : myJid;
                console.log(`[Bridge] Received incoming command from user (Type: ${messageType})`);
                await notifyPython({
                    event: 'incoming_message',
                    msgId,
                    senderJid: effectiveSender,
                    messageType,
                    textContent: trimmedText,
                    audioFilePath,
                    timestamp: msg.messageTimestamp
                });

            } catch (err) {
                console.error('[Bridge] Error handling message:', err);
            }
        }
    });
}

// Internal HTTP Server for Python to command the Bridge
const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host}`);

    if (req.method === 'GET' && url.pathname === '/status') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: connectionStatus, myJid }));
        return;
    }

    if (req.method === 'POST' && url.pathname === '/send-text') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', async () => {
            try {
                const { jid, text } = JSON.parse(body);
                const targetJid = (jid && !jid.endsWith('@lid')) ? jid : myJid;
                if (!sock || connectionStatus !== 'connected') {
                    res.writeHead(503, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'WhatsApp not connected' }));
                    return;
                }

                // Pre-generate unique message ID starting with BOT_ so upsert can never process it
                const msgId = 'BOT_' + Date.now() + '_' + crypto.randomBytes(8).toString('hex').toUpperCase();
                botSentMessageIds.add(msgId);
                messageStore.set(msgId, { conversation: text });

                // Send typing indicator
                await sock.sendPresenceUpdate('composing', targetJid);
                const sent = await sock.sendMessage(targetJid, { text }, { messageId: msgId });
                if (sent?.message) {
                    messageStore.set(msgId, sent.message);
                }
                await sock.sendPresenceUpdate('paused', targetJid);

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, messageId: msgId }));
            } catch (err) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }

    if (req.method === 'POST' && url.pathname === '/send-file') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', async () => {
            try {
                const { jid, filePath, fileName, caption, mimetype } = JSON.parse(body);
                const targetJid = (jid && !jid.endsWith('@lid')) ? jid : myJid;
                if (!sock || connectionStatus !== 'connected') {
                    res.writeHead(503, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'WhatsApp not connected' }));
                    return;
                }

                if (!fs.existsSync(filePath)) {
                    res.writeHead(404, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'File not found' }));
                    return;
                }

                const fileBuffer = fs.readFileSync(filePath);
                const resolvedMime = mimetype || 'application/pdf';
                const displayName = fileName || path.basename(filePath);

                const msgId = 'BOT_' + Date.now() + '_' + crypto.randomBytes(8).toString('hex').toUpperCase();
                botSentMessageIds.add(msgId);

                const sent = await sock.sendMessage(targetJid, {
                    document: fileBuffer,
                    mimetype: resolvedMime,
                    fileName: displayName,
                    caption: caption || ''
                }, { messageId: msgId });

                if (sent?.message) {
                    messageStore.set(msgId, sent.message);
                }

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, messageId: msgId }));
            } catch (err) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not Found' }));
});

server.listen(BRIDGE_PORT, '127.0.0.1', () => {
    console.log(`[Bridge] Micro-service listening on http://127.0.0.1:${BRIDGE_PORT}`);
    startSock();
});
