.PHONY: install train resume eval app api predict test clean db compose-up compose-down download-na-freshwater

install:
	venv/bin/pip install -r requirements.txt

test:
	venv/bin/python -m pytest

train:
	venv/bin/python -m services.fish_ai.training.train --config configs/training.yaml

resume:
	venv/bin/python -m services.fish_ai.training.train --config configs/training.yaml --resume

eval:
	venv/bin/python -m services.fish_ai.training.evaluate --config configs/training.yaml

app:
	venv/bin/streamlit run apps/omyfish_web/main.py

api:
	venv/bin/uvicorn apps.omyfish_api.main:app --reload --host 0.0.0.0 --port 8000

predict:
	venv/bin/python -m services.fish_ai.predictors.efficientnet --image $(IMAGE)

db:
	docker compose -f infrastructure/docker/docker-compose.yml up postgis -d

compose-up:
	docker compose -f infrastructure/docker/docker-compose.yml up --build -d

compose-down:
	docker compose -f infrastructure/docker/docker-compose.yml down

download-na-freshwater:
	venv/bin/python research/scripts/download_data.py download-na-freshwater --count $(or $(COUNT),400)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
