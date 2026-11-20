"""SQLite coordinates immutable artifact and history records across processes."""
from __future__ import annotations
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from .common import digest, encode, now

SCHEMA = '''
CREATE TABLE IF NOT EXISTS works(id TEXT PRIMARY KEY, uri TEXT UNIQUE NOT NULL, revision INTEGER NOT NULL,
 archived_at TEXT);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
 kind TEXT NOT NULL, xml_hash TEXT NOT NULL, pdf_hash TEXT NOT NULL, metadata TEXT NOT NULL, created TEXT NOT NULL,
 archived_at TEXT);
CREATE TABLE IF NOT EXISTS manifests(id TEXT NOT NULL, revision INTEGER NOT NULL, work_id TEXT NOT NULL REFERENCES works(id),
 source_id TEXT NOT NULL REFERENCES sources(id), body TEXT NOT NULL, created TEXT NOT NULL, actor TEXT NOT NULL,
 reason TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE IF NOT EXISTS expressions(id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id), parent_id TEXT,
 effective_date TEXT NOT NULL, xml_hash TEXT NOT NULL, canonical_hash TEXT NOT NULL, manifest_hash TEXT NOT NULL,
 body TEXT NOT NULL, created TEXT NOT NULL, approved_at TEXT, approved_by TEXT, invalidated_at TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
 kind TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS expression_timeline ON expressions(work_id,effective_date,created);
CREATE TABLE IF NOT EXISTS related_documents(id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
 title TEXT NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL, document_date TEXT NOT NULL,
 pdf_hash TEXT NOT NULL, created TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reader_issues(id INTEGER PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
 expression_id TEXT NOT NULL, message TEXT NOT NULL, created TEXT NOT NULL);
'''


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.artifacts = self.directory / 'artifacts'
        self.artifacts.mkdir(exist_ok=True)
        with closing(self.connect()) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError(f'Unsupported consolidation database version {version}')
            db.executescript(SCHEMA)
            if version == 1:
                db.execute('ALTER TABLE works ADD COLUMN archived_at TEXT')
                db.execute('ALTER TABLE sources ADD COLUMN archived_at TEXT')
            db.execute('PRAGMA user_version=2')
            db.commit()

    def connect(self):
        db = sqlite3.connect(self.directory / 'history.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, raw):
        key = digest(raw)
        path = self.artifacts / key
        try:
            with path.open('xb') as stream:
                stream.write(raw)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError('Artifact hash collision or corruption')
        return key

    def read(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid artifact hash')
        raw = (self.artifacts / key).read_bytes()
        if digest(raw) != key:
            raise ValueError('Artifact integrity check failed')
        return raw

    @staticmethod
    def event(db, work_id, kind, actor, reason, body):
        db.execute('INSERT INTO events(work_id,kind,actor,reason,created,body) VALUES(?,?,?,?,?,?)',
                   (work_id, kind, actor, reason, now(), encode(body).decode()))

    @staticmethod
    def load(row):
        if row is None:
            raise ValueError('Record not found')
        result = dict(row)
        for key in ('body', 'metadata'):
            if key in result:
                result[key] = json.loads(result[key])
        return result
