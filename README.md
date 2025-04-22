
# RAG demo w/ CockroachDB

## create a cockroachdb cluster and set environment variables
Create a v25.1+ Cockroachdb Cluster and set DATABASE_URL environment variable
```bash
## set OpenAI API Key
export DATABASE_URL=
export OPENAI_API_KEY=
```

## create virtual environment for data loader and api server. Activiate each environment
python3 -m venv venv 
source venv/bin/activate
python -m pip install requirements.txt

## create schema and load embeddings
```bash
python create-embeddings.py --mdfile vector.md --url 'https://www.cockroachlabs.com/docs/v24.3/vector.html'
python create-embeddings.py --mdfile defaultpriv.md --url 'https://docs.google.com/document/d/1nOf_vjxhOXdsI7Qq596UE7Ih7IvWbFus7NeL_dC5OdY/edit?usp=sharing' --delimiter '## '
python create-embeddings.py --mdfile changefeederr.md --url 'https://cockroachlabs.atlassian.net/wiki/spaces/CKB/pages/2839838826/Runbook+Fix+Changefeeds+error+Message+was+too+large'
```
## create api key table & key
`create-embeddings.py` creates the schema for embeddings and api_keys. Create an active API key.
```sql
insert into api_keys (key, user_id, is_active) values ('<rag_api_key>', '<username>', true); 
 ```

## run fastapi server
In `api` folder start the server
```bash
cd api
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## start localhost for index.html
update <rag_api_key> in index.html 
```bash
cd frontend
python3 -m http.server 8001
```

# test fastapi 
curl -H "X-API-Key: <rag_api_key>" \
     "http://localhost:8000/rag?question=What%20is%20vector%20data%20type"
