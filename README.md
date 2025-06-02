
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
python -m pip install -r requirements.txt

## crawl documents as markdown
python -m pip install -U crawl4ai
crawl4ai-setup
crawl4ai-doctor 

crwl https://www.cockroachlabs.com/docs/v25.2/vector-indexes.html -o markdown > vector.md

## create schema and load embeddings


```bash
python create-embeddings.py --mdfile vector.md --url 'https://www.cockroachlabs.com/docs/v25.2/vector.html'
python create-embeddings.py --mdfile vector-index.md --url 'https://www.cockroachlabs.com/docs/v25.2/vector-indexes.html'
python create-embeddings.py --mdfile changefeederr.md --url 'https://cockroachlabs.atlassian.net/wiki/spaces/CKB/pages/2839838826/Runbook+Fix+Changefeeds+error+Message+was+too+large'
python create-embeddings.py --mdfile defaultpriv.md --url 'https://docs.google.com/document/d/1nOf_vjxhOXdsI7Qq596UE7Ih7IvWbFus7NeL_dC5OdY/edit?usp=sharing'
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
```bash
curl -H "Authorization: Bearer test_<api-key>" \
     "http://localhost:8000/rag?question=What%20is%20vector%20data%20type"
```
# docker
Download ca.crt from CockroachCloud and copy it to app/api
```bash
cd app/api
source venv/bin/activate
python -m pip freeze > requirements.txt
docker buildx create --use  # Only need to do this once
# docker buildx build --platform linux/amd64,linux/arm64
docker build -t waterg2008/rag:v0.1 . 
docker run  -p 8000:8000  -e DATABASE_URL=$DATABASE_URL_DOCKER -e OPENAI_API_KEY=$OPENAI_API_KEY waterg2008/rag:v0.1
```

# test fastapi 
curl -H "Authorization: Bearer test_<api-key>" \
     "http://localhost:8000/rag?question=What%20is%20vector%20data%20type"

# use gcloud and test api endpoint
```bash
gcloud auth login
gcloud config set project your-project-id
gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com run.googleapis.com
gcloud artifacts repositories create docker-repo \
    --repository-format=docker \
    --location=us-west1 \
    --project=cockroach-lin \
    --description="My Docker repository"

gcloud auth configure-docker us-west1-docker.pkg.dev
docker build -t waterg2008/rag:v0.1 . --platform linux/amd64
docker tag waterg2008/rag:v0.1 us-west1-docker.pkg.dev/cockroach-lin/docker-repo/rag:v0.1
docker push us-west1-docker.pkg.dev/cockroach-lin/docker-repo/rag:v0.1
gcloud artifacts docker images list us-west1-docker.pkg.dev/cockroach-lin/docker-repo

gcloud run deploy rag \
    --image=us-west1-docker.pkg.dev/cockroach-lin/docker-repo/rag:v0.1 \
    --region=us-west1 \
    --platform=managed \
    --set-env-vars=DATABASE_URL=$DATABASE_URL_DOCKER,OPENAI_API_KEY=$OPENAI_API_KEY \
    --allow-unauthenticated \
    --port 8000 \
    --cpu 2 \
    --memory 2Gi \
    --max-instances 1

curl -H "Authorization: Bearer test_<api-key>" \
     "http://<url>.us-west1.run.app/rag?question=What%20is%20vector%20data%20type"
```