#!/usr/bin/env python
# coding: utf-8

import os
from openai import OpenAI
from glob import glob
from sentence_transformers import SentenceTransformer
import psycopg
from psycopg.rows import namedtuple_row

model = SentenceTransformer("all-MiniLM-L6-v2")

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),  # This is the default and can be omitted
)

def generate_sql (question):
    context = """
    The table you'll query is defined as 
        CREATE TABLE IF NOT EXISTS public.embeddings  (
                     id UUID NOT NULL, 
                     version STRING NULL,
                     url STRING NULL,
                     text STRING NULL,
                     embedding VECTOR(384) NULL,
                     CONSTRAINT embeddings_pkey PRIMARY KEY (id ASC)
                 );
    column version is the CockroachDB version, column url contains the url of the document, column text has the human readable document, and column embedding contains the vectorize the document chunk of column text.
    """
    SYSTEM_PROMPT = """
    Human: You are an SQL statement writer. Return a sql statement from the contextual passage snippets provided.
    """
    USER_PROMPT = f"""
    Use the following pieces of information enclosed in <context> tags to write a sql statement that can be executed on the public.embeddings to the question enclosed in <question> tags.
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
    return {"answer": answer}


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


def retrieve_similar_texts(query, crdb_ver, k=3):
    """Retrieve the top-k most similar texts from pgvector."""
    # embedding = model.encode(query).tolist()
    # embedding = response['data'][0]['embedding']
    # using openai embedding api
    response = client.embeddings.create(
    input=[query],
        model="text-embedding-ada-002"  # This is the current recommended embedding model
    )

    # Extract the embedding vector
    embedding = response.data[0].embedding
    embedding_str = f"[{','.join(map(str, embedding))}]"  # Format for SQL
    db_url = os.environ.get("DATABASE_URL")
    conn = psycopg.connect(db_url, 
                    application_name="generate_response", 
                    row_factory=namedtuple_row)

    print (embedding_str)
    with conn.cursor() as cursor:
        cursor.execute(f"""
            SELECT url, text, embedding <=> %s AS similarity
            FROM embeddings
            WHERE version = %s
            ORDER BY embedding <=> %s DESC
            LIMIT %s;
        """, (embedding_str, crdb_ver, embedding_str, k))
    
        results = cursor.fetchall()
    return results

def generate_rag_response(question, k=3):
    """Retrieve relevant documents and generate a response using GPT, showing source IDs."""
    retrieved_texts = retrieve_similar_texts(question, "v24.3", k)

    if not retrieved_texts:
        return {"answer": "I couldn't find relevant information in the database.", "sources": []}

    # print(context)
    # Extract IDs and texts separately
    urls = [str(row[0]) for row in retrieved_texts]
    texts = [row[1] for row in retrieved_texts]
    similarities = [str(row[2]) for row in retrieved_texts]

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
    return {"answer": answer, "urls": urls, "similarities": similarities}

def main():
    # question = "How does Vector data type help developers build AI applications?"
    # question = "does cockroachdb support vector data type"
    question = "how to use default privilege on cockroachdb"
    result = generate_rag_response(question)
    print("📝 Generated RAG Response:")
    print(result["answer"])
    print("\n📌 Retrieved Text IDs:", result["urls"], result["similarities"])

if __name__=="__main__":
    main()

# Example interactive loop
# while True:
#     user_query = input("\n🔍 Enter your question (or type 'exit' to quit): ")
#     if user_query.lower() == "exit":
#         break

#     # result = generate_rag_response(user_query)
#     result = generate_sql (user_query)
#     print("\n📝 Generated Response:")
#     print(result["answer"])
#     # print("\n📌 Retrieved Text IDs:", result["urls"], result["similarities"])
