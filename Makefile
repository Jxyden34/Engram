.PHONY: up down logs ps pull-model admin backup

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=150

ps:
	docker compose ps

pull-model:
	docker compose exec ollama ollama pull $${EMBEDDING_MODEL:-all-minilm}

admin:
	docker compose exec api python scripts/create_admin.py

backup:
	docker compose restart db-backup object-backup
