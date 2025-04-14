#!/usr/bin/env python
# coding: utf-8
import argparse
import os
from glob import glob
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import uuid
import logging, psycopg
from psycopg.rows import namedtuple_row
import numpy as np

def create_schema (conn):

    conn.autocommit = True
    with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS public.embeddings  (
                     id UUID NOT NULL, 
                     version STRING NULL,
                     url STRING NULL,
                     text STRING NULL,
                     embedding VECTOR(384) NULL,
                     CONSTRAINT embeddings_pkey PRIMARY KEY (id ASC)
                 );""" )
            logging.debug("create embeddings tables: status message: %s",
                          cur.statusmessage)
            
            cur.execute(
                """CREATE TABLE IF NOT EXISTS api_keys (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    key TEXT NOT NULL UNIQUE,
                    user_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT now()
                 );""" )
            logging.debug("create api keys table: status message: %s",
                          cur.statusmessage)
    return

model = SentenceTransformer("all-MiniLM-L6-v2")

def chunking(mdfile, delimiter):
    text_lines = []
    for file_path in glob(mdfile, recursive=True):
        with open(file_path, "r") as file:
            file_text = file.read()
        text_lines += file_text.split(delimiter)
    return text_lines

def test():
    test_embedding = model.encode("CockroachDB test")
    embedding_dim = len(test_embedding)
    print(embedding_dim)
    print(test_embedding[:10])

def normalize_vector(vec):
    return (vec / np.linalg.norm(vec)).tolist()  # Normalize to unit length

def insert_embeddings (conn, text_lines, version, url):
    conn.autocommit = True
    with conn.cursor() as cur:
        for i, line in enumerate(tqdm(text_lines, desc="Creating embeddings")):
            id = uuid.uuid4()
            # Insert the embedding
            # embedding = normalize_vector(model.encode(line))
            embedding = normalize_vector(model.encode(line))
            # Convert list to PostgreSQL-compatible format
            embedding_str = f"[{','.join(map(str, embedding))}]"
            cur.execute(
                "INSERT INTO embeddings (id, version, url, text, embedding) VALUES (%s, %s, %s, %s, %s)",
                (id, version, url, line, embedding_str)
            )
            # conn.commit()
            # logging.debug("create_accounts(): status message: %s",
                          # cur.statusmessage)
    return len(text_lines)

def main():
    parser = argparse.ArgumentParser(description="Process markdown file for embeddings.")
    parser.add_argument("--mdfile", required=True, help="Path to the markdown file to process")
    parser.add_argument("--delimiter", default="# ", help="Delimiter to split the markdown file (default: '# ')")
    parser.add_argument("--version", default="v24.3", help="Version of cockroachdb")
    parser.add_argument("--url", required=True, help="URL of the markdown file")

    args = parser.parse_args()

    # logging.basicConfig(level=logging.DEBUG if opt.verbose else logging.INFO)
    try:
        # Attempt to connect to cluster with connection string provided to
        # script. By default, this script uses the value saved to the
        # DATABASE_URL environment variable.
        # For information on supported connection string formats, see
        # https://www.cockroachlabs.com/docs/stable/connect-to-the-database.html.
        db_url = os.environ.get("DATABASE_URL")
        conn = psycopg.connect(db_url,
                            application_name="$play_create_embeddings", 
                            row_factory=namedtuple_row)
        create_schema(conn)
        text_lines = chunking(args.mdfile, args.delimiter)
        insert_embeddings(conn, text_lines, args.version, args.url)
    except Exception as e:
        logging.fatal("database connection failed")
        logging.fatal(e)   

if __name__=="__main__":
    main()