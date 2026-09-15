IMPORTANT - do this part first, right now, regardless of this file:
Run this once in your Supabase SQL Editor to fix your LIVE database
immediately (this is what's actually crashing Collaborate right now):

  ALTER TABLE collab_answers ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES collab_answers(id);

That alone fixes the live crash. Everything below is the code fix so
this class of mistake (a column added to an existing table) can't
silently break production again on a future update.

Overwrite backend/db.py with the one in this folder, then:
  git add backend/db.py
  git commit -m "Self-heal missing columns on app startup instead of just create_all()"
  git push origin main

What changed: init_db() (already called on startup by both app.py and
api_server.py) now also checks for a few known columns and adds them
via ALTER TABLE if a table already exists but is missing one -
Base.metadata.create_all() only creates brand-new tables, it never
alters ones already in the live database, which is exactly how the
parent_id column silently never made it into your production
database. Verified against a simulated copy of your actual
pre-migration table.
