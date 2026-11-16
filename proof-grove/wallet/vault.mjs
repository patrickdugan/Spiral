/* Wallet secrets stay in an authenticated encrypted SQLite blob. Public metadata
 * holds only a random salt and a short process lease. Every preview save commits
 * before an external mint request, so a lost response does not lose its secrets.
 */
import { DatabaseSync } from 'node:sqlite';
import { randomBytes, randomUUID, scryptSync, createCipheriv, createDecipheriv } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

const AAD = Buffer.from('proof-grove/cashu-wallet/v1');
export class Vault {
  constructor(filename,password) {
    if(typeof password !== 'string' || password.length < 16) throw new Error('Wallet passphrase must have at least 16 characters');
    mkdirSync(dirname(filename),{recursive:true});
    this.db = new DatabaseSync(filename);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS vault (id INTEGER PRIMARY KEY CHECK(id=1), salt BLOB NOT NULL, ciphertext BLOB);
      CREATE TABLE IF NOT EXISTS lease (id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT, until_ms INTEGER NOT NULL DEFAULT 0);`);
    this.db.prepare('INSERT OR IGNORE INTO vault VALUES(1,?,NULL)').run(randomBytes(32));
    this.db.prepare('INSERT OR IGNORE INTO lease VALUES(1,NULL,0)').run();
    this.key = scryptSync(password,Buffer.from(this.db.prepare('SELECT salt FROM vault WHERE id=1').get().salt),32);
    this.owner = null;
  }
  close() { this.key.fill(0); this.db.close(); }
  load() {
    const blob = this.db.prepare('SELECT ciphertext FROM vault WHERE id=1').get().ciphertext;
    if(blob === null) return {schema:'proof-grove/wallet/v1',operations:{}};
    try {
      const bytes = Buffer.from(blob);
      const decipher = createDecipheriv('aes-256-gcm',this.key,bytes.subarray(0,12));
      decipher.setAAD(AAD); decipher.setAuthTag(bytes.subarray(12,28));
      return JSON.parse(Buffer.concat([decipher.update(bytes.subarray(28)),decipher.final()]).toString('utf8'));
    } catch { throw new Error('Wallet passphrase is incorrect or the encrypted vault was modified'); }
  }
  save(state) {
    if(!this.owner) throw new Error('Wallet mutation requires its process lease');
    const nonce = randomBytes(12), cipher = createCipheriv('aes-256-gcm',this.key,nonce); cipher.setAAD(AAD);
    const ciphertext = Buffer.concat([cipher.update(JSON.stringify(state),'utf8'),cipher.final()]);
    const blob = Buffer.concat([nonce,cipher.getAuthTag(),ciphertext]);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const lease = this.db.prepare('SELECT owner,until_ms FROM lease WHERE id=1').get();
      if(lease.owner !== this.owner || lease.until_ms <= Date.now()) throw new Error('Wallet process lease expired; reload before continuing');
      this.db.prepare('UPDATE vault SET ciphertext=? WHERE id=1').run(blob);
      this.db.prepare('UPDATE lease SET until_ms=? WHERE id=1').run(Date.now()+180_000);
      this.db.exec('COMMIT');
    } catch(error) { this.db.exec('ROLLBACK'); throw error; }
  }
  async exclusive(fn) {
    if(this.owner) throw new Error('Wallet operation is already running');
    const owner=randomUUID();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const old=this.db.prepare('SELECT until_ms FROM lease WHERE id=1').get();
      if(old.until_ms > Date.now()) throw new Error('Another wallet process is active; retry after its lease expires');
      this.db.prepare('UPDATE lease SET owner=?,until_ms=? WHERE id=1').run(owner,Date.now()+180_000);
      this.db.exec('COMMIT'); this.owner=owner;
    } catch(error) { this.db.exec('ROLLBACK'); throw error; }
    try { return await fn(); }
    finally { this.db.prepare('UPDATE lease SET owner=NULL,until_ms=0 WHERE id=1 AND owner=?').run(owner); this.owner=null; }
  }
}
