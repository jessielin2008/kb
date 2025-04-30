#!/usr/bin/env python
# coding: utf-8
import argparse
import os
from glob import glob
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import uuid
import logging, psycopg
from psycopg.rows import namedtuple_row
import numpy as np

def create_schema (conn):

    conn.autocommit = True
    with conn.cursor() as cur:
            # openai embeddings has 1536 dimensions, while SentenceTransformer has 384
            cur.execute(
                """CREATE TABLE IF NOT EXISTS public.embeddings  (
                     id UUID NOT NULL, 
                     version STRING NULL,
                     url STRING NULL,
                     text STRING NULL,
                     embedding VECTOR(1536) NULL ,
                     CONSTRAINT embeddings_pkey PRIMARY KEY (id ASC),
                     VECTOR INDEX (version, embedding)
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
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def test():
    test_str = "CockroachDB test"

    embedding = model.encode(test_str)
    print(f"Embedding length: {len(embedding)}")
    print("First few values:", embedding[:5])

    response = client.embeddings.create(
        input=[test_str],
        model="text-embedding-ada-002"  # This is the current recommended embedding model
    )
    # Extract the embedding vector
    embedding = response.data[0].embedding
    print(f"Embedding length: {len(embedding)}")
    print("First few values:", embedding[:5])

def chunking(mdfile, delimiter):
    text_lines = []
    for file_path in glob(mdfile, recursive=True):
        with open(file_path, "r") as file:
            file_text = file.read()
        text_lines += file_text.split(delimiter)
        print (f"File: {file_path}, Number of lines: {len(text_lines)}")
    return text_lines

def normalize_vector(vec):
    return (vec / np.linalg.norm(vec)).tolist()  # Normalize to unit length

def insert_embeddings (conn, text_lines, version, url):
    conn.autocommit = True
    with conn.cursor() as cur:
        for i, line in enumerate(tqdm(text_lines, desc="Creating embeddings")):
            id = uuid.uuid4()
            logging.info("insert_embeddings(): %s", line[0:20])
            # Insert the embedding
            # embedding = normalize_vector(model.encode(line))
            # embedding = response['data'][0]['embedding']
 
            # Call OpenAI Embeddings API
            response = client.embeddings.create(
                input=[line],
                model="text-embedding-ada-002"  # This is the current recommended embedding model
            )
            embedding = response.data[0].embedding
            
            # Convert list to PostgreSQL-compatible format
            embedding_str = f"[{','.join(map(str, embedding))}]"
            cur.execute(
                "INSERT INTO embeddings (id, version, url, text, embedding) VALUES (%s, %s, %s, %s, %s)",
                (id, version, url, line, embedding_str)
            )
            # conn.commit()
            logging.debug("insert_embeddings(): status message: %s",
                          cur.statusmessage)
    return len(text_lines)

def main():
    parser = argparse.ArgumentParser(description="Process markdown file for embeddings.")
    parser.add_argument("--mdfile", required=True, help="Path to the markdown file to process")
    parser.add_argument("--url", required=True, help="URL of the markdown file")
    parser.add_argument("--delimiter", default="# ", help="Delimiter to split the markdown file (default: '# ')")
    parser.add_argument("--version", default="v24.3", help="Version of cockroachdb (default: v24.3)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    try:
        # Attempt to connect to cluster with connection string provided to
        # script. By default, this script uses the value saved to the
        # DATABASE_URL environment variable.
        # For information on supported connection string formats, see
        # https://www.cockroachlabs.com/docs/stable/connect-to-the-database.html.
        db_url = os.environ.get("DATABASE_URL")
        conn = psycopg.connect(db_url,
                            application_name="create_embeddings", 
                            row_factory=namedtuple_row)
        create_schema(conn)
        text_lines = chunking(args.mdfile, args.delimiter)
        insert_embeddings(conn, text_lines, args.version, args.url)
    except Exception as e:
        logging.fatal("database connection failed")
        logging.fatal(e)   

if __name__=="__main__":
    main()