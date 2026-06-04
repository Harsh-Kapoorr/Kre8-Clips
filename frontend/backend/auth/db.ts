import Database from "better-sqlite3"
import path from "path"
import { mkdirSync } from "fs"

function getDb() {
  const dataDir = path.join(process.cwd(), "data")
  mkdirSync(dataDir, { recursive: true })
  const db = new Database(path.join(dataDir, "kre8.db"))
  db.pragma("journal_mode = WAL")
  
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT,
      name TEXT NOT NULL,
      plan TEXT DEFAULT 'free' NOT NULL,
      clips_used INTEGER DEFAULT 0 NOT NULL,
      deepgram_key TEXT,
      gemini_key TEXT,
      provider TEXT DEFAULT 'email',
      google_id TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS sessions (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      refresh_token TEXT UNIQUE NOT NULL,
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
  `)
  
  return db
}

export const db = getDb()

function generateId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0
    const v = c === "x" ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}

export function createUser(email: string, passwordHash: string | null, name: string, provider = "email", googleId?: string) {
  const now = new Date().toISOString()
  const id = generateId()
  const stmt = db.prepare(`
    INSERT INTO users (id, email, password_hash, name, plan, clips_used, provider, google_id, created_at, updated_at)
    VALUES (?, ?, ?, ?, 'free', 0, ?, ?, ?, ?)
  `)
  stmt.run(id, email.toLowerCase(), passwordHash, name, provider, googleId ?? null, now, now)
  return { id, email: email.toLowerCase(), name, plan: "free", clips_used: 0, provider }
}

export function findUserByEmail(email: string) {
  const stmt = db.prepare("SELECT * FROM users WHERE email = ?")
  return stmt.get(email.toLowerCase()) as any
}

export function findUserById(id: string) {
  const stmt = db.prepare("SELECT id, email, name, plan, clips_used, deepgram_key, gemini_key, created_at FROM users WHERE id = ?")
  return stmt.get(id) as any
}

export function updateUserApiKeys(userId: string, deepgramKey: string, geminiKey: string) {
  const now = new Date().toISOString()
  const stmt = db.prepare("UPDATE users SET deepgram_key = ?, gemini_key = ?, updated_at = ? WHERE id = ?")
  stmt.run(deepgramKey, geminiKey, now, userId)
}

export function incrementClipsUsed(userId: string) {
  const now = new Date().toISOString()
  const stmt = db.prepare("UPDATE users SET clips_used = clips_used + 1, updated_at = ? WHERE id = ?")
  stmt.run(now, userId)
}

export function updateUserPlan(userId: string, plan: string) {
  const now = new Date().toISOString()
  const stmt = db.prepare("UPDATE users SET plan = ?, updated_at = ? WHERE id = ?")
  stmt.run(plan, now, userId)
}

export function createSession(userId: string, refreshToken: string) {
  const now = new Date()
  const expiresAt = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000)
  const id = generateId()
  const stmt = db.prepare(`
    INSERT INTO sessions (id, user_id, refresh_token, expires_at, created_at)
    VALUES (?, ?, ?, ?, ?)
  `)
  stmt.run(id, userId, refreshToken, expiresAt.toISOString(), now.toISOString())
  return { id, refreshToken, expiresAt: expiresAt.toISOString() }
}

export function findSessionByToken(token: string) {
  const stmt = db.prepare("SELECT * FROM sessions WHERE refresh_token = ? AND expires_at > ?")
  return stmt.get(token, new Date().toISOString()) as any
}

export function deleteSession(token: string) {
  const stmt = db.prepare("DELETE FROM sessions WHERE refresh_token = ?")
  stmt.run(token)
}

export function deleteAllUserSessions(userId: string) {
  const stmt = db.prepare("DELETE FROM sessions WHERE user_id = ?")
  stmt.run(userId)
}