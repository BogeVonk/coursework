import psycopg2
from pathlib import Path
from config import DB_NAME, DB_PARAMS
from psycopg2 import sql
params = DB_PARAMS
conn=psycopg2.connect(dbname='postgres',**params); conn.autocommit=True
cur=conn.cursor(); cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DB_NAME,))
if cur.fetchone() is None: cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DB_NAME)))
cur.close(); conn.close()
conn=psycopg2.connect(dbname=DB_NAME,**params)
with conn.cursor() as cur: cur.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
conn.commit(); conn.close(); print('Database and 11 tables are ready')
