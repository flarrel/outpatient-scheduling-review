# Outpatient Scheduling Review

A local prototype for outpatient scheduling coordinators. It imports simulated hospital scheduling, appointment, and finance-system feeds, then ranks booked appointments for manual reminder review. The handbook view returns cited excerpts from synthetic operating procedures.

The data and procedures are fictional. The prototype is for technical evaluation with synthetic records.

## Run locally

Use Python 3.12. From the repository root:

```sh
python3 -m venv ../.venv
../.venv/bin/python -m pip --cache-dir ../cache/pip install -r requirements.txt
../.venv/bin/python -m outpatient fixtures
../.venv/bin/python -m outpatient ingest
../.venv/bin/python -m outpatient serve
```

Open [the local review queue](http://127.0.0.1:8080). The queue runs immediately. To enable handbook answers, follow the model setup below.

### Enable the handbook model on Apple Silicon

Download and verify the pinned llama.cpp runner and Qwen2.5-0.5B model (about 508 MB combined):

```sh
./scripts/setup-model.sh
```

Start the model server in a separate terminal. Choose a local API key and set `MODEL_API_KEY` to that value in both terminals.

```sh
../cache/llama/llama-b12803/llama-server \
  --model ../cache/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 --port 8090 --ctx-size 2048 --threads 4 \
  --no-ui --api-key "$MODEL_API_KEY"
```

Start or restart the app:

```sh
MODEL_URL=http://127.0.0.1:8090 ../.venv/bin/python -m outpatient serve
```

## Simulated integrations

Start `../.venv/bin/python -m outpatient mock` in a terminal, then import from it in another:

```sh
../.venv/bin/python -m outpatient ingest --source-url http://127.0.0.1:8091
../.venv/bin/python -m outpatient summary
```

The HTTP fixture service exposes an HIS-style scheduling export, a FHIR R4 Appointment bundle, and a Business Central-style department dimension feed. Each import validates the three snapshots before replacing SQLite data. The workflow is read-only with respect to the source feeds.

## Evaluate

```sh
../.venv/bin/python -m unittest discover -s tests -v
../.venv/bin/python -m outpatient evaluate-ml
MODEL_URL=http://127.0.0.1:8090 ../.venv/bin/python -m outpatient evaluate-rag \
  --output ../artifacts/rag-evaluation.json
```

See [the evaluation report](docs/evaluation.md) and [the walkthrough](docs/walkthrough.md).

## Container and local Kubernetes

Docker runs the same app and generates its own synthetic snapshot at startup. The default image includes the queue and handbook retrieval code. Model-backed answers require a separately reachable llama.cpp endpoint and `MODEL_URL` and `MODEL_API_KEY` where applicable. Use the native setup for the complete demo.

```sh
docker build -t outpatient-review:local .
docker run --rm -p 127.0.0.1:8080:8080 outpatient-review:local
```

With Docker, `kind`, and `kubectl` available:

```sh
mkdir -p ../cache
kubeconfig="$PWD/../cache/outpatient-kubeconfig"
kind create cluster --name outpatient-review --kubeconfig "$kubeconfig"
kind load docker-image outpatient-review:local --name outpatient-review
kubectl --kubeconfig "$kubeconfig" apply -f deploy/kubernetes.yaml
kubectl --kubeconfig "$kubeconfig" rollout status deployment/outpatient-review
kubectl --kubeconfig "$kubeconfig" port-forward service/outpatient-review 8080:8080
```

Use `curl http://127.0.0.1:8080/health` to check the running service. Stop the port forward and run `kind delete cluster --name outpatient-review --kubeconfig "$kubeconfig"` when done.
