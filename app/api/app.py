#!/usr/bin/env python
# coding: utf-8
from fastapi import FastAPI
from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from openai import OpenAI
from glob import glob
from sentence_transformers import SentenceTransformer
from psycopg_pool import ConnectionPool
from psycopg.rows import namedtuple_row
from fastapi.middleware.cors import CORSMiddleware
import logging

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,  # You can change to INFO in production
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()

# model = SentenceTransformer("all-MiniLM-L6-v2")

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),  # This is the default and can be omitted
)

# Initialize FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
pool = ConnectionPool(conninfo=os.environ.get("DATABASE_URL"),
                      kwargs={"application_name": "chatbot",
                              "keepalives": 1,
                              "keepalives_idle": 60,
                              "keepalives_interval": 10,
                              "keepalives_count": 5},
                      max_lifetime=600        # 10 minutes
                      )

def generate_response(question):
    
    SYSTEM_PROMPT = """
    Human: You are an AI assistant. You are able to find answers to the questions from the contextual passage snippets provided.
    """
    USER_PROMPT = f"""
    Provide an answer to the question enclosed in <question> tags.
    <question>
    {question}
    </question>
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
    )
    answer = response.choices[0].message.content
    return {"answer": answer}


def retrieve_similar_texts(query, crdb_ver, conn, k=3):
    """Retrieve the top-k most similar texts from pgvector."""
    # embedding = model.encode(query).tolist()
    response = client.embeddings.create(
        input=[query],
        model="text-embedding-ada-002"  # This is the current recommended embedding model
    )

    # Extract the embedding vector
    embedding = response.data[0].embedding

    embedding_str = f"[{','.join(map(str, embedding))}]"  # Format for SQL

    # print (embedding_str)
    with conn.cursor() as cursor:
        cursor.execute(f"""
            SELECT url, text, embedding <-> %s AS distance, id
            FROM embeddings
            WHERE version = %s
            ORDER BY embedding <-> %s
            LIMIT %s;
        """, (embedding_str, crdb_ver, embedding_str, k))
        logger.debug(f"""
            SELECT url, text, embedding <-> %s AS distance, id
            FROM embeddings
            WHERE version = %s
            ORDER BY embedding <-> %s
            LIMIT %s;
        """, (embedding_str, crdb_ver, embedding_str, k))
        results = cursor.fetchall()
    return results

def generate_rag_response(conn, question, k=3):

    """Retrieve relevant documents and generate a response using GPT, showing source IDs."""
    retrieved_texts = retrieve_similar_texts(question, "v25.2", conn, k)

    if not retrieved_texts:
        return {"answer": "I couldn't find relevant information in the database.", "sources": []}

    # print(context)
    # Extract IDs and texts separately
    urls = [str(row[0]) for row in retrieved_texts]
    texts = [row[1] for row in retrieved_texts]
    ids = [str(row[3]) for row in retrieved_texts]

    # Combine retrieved texts for the prompt
    context = "\n".join(texts)
    
    SYSTEM_PROMPT = """
    Human: You are an AI assistant. You are able to find answers to the questions from the contextual passage snippets provided.
    """
    USER_PROMPT = f"""
    Use the following pieces of information enclosed in <context> tags to provide an answer to the question enclosed in <question> tags.
    <context>
    {context}
    </context>
    <question>
    {question}
    </question>
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
    )
    answer = response.choices[0].message.content
    return {"answer": answer, "urls": urls, "ids": ids}

def validate_api_key(api_key: str) -> bool:
    with pool.connection() as conn:
        with conn.cursor() as cursor:
            try:
                query = """
                SELECT * FROM api_keys
                WHERE key = %s AND is_active = TRUE
                LIMIT 1;
                """
                cursor.execute(query, (api_key,))
                result = cursor.fetchone()
                logger.debug(f"query is {query} and key is {api_key}")
                return result is not None  # True if key is valid and active

            except Exception as e:
                print(f"[ERROR] API key validation failed: {e}")
                return False
 
def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not validate_api_key(credentials.credentials):
        raise HTTPException(status_code=403, detail="Invalid API Key")
   
@app.get("/rag")
def query_rag(question: str, api_check: bool = Depends(verify_api_key)):
    """API endpoint for querying the RAG system."""
    with pool.connection() as conn:
        response = generate_rag_response(conn, question)
    return response
