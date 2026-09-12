.PHONY: up down logs ps pull-model admin backup dr-status dr-test dr-replicate

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


dr-status:
	docker compose exec db sh -lc 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "SELECT artifact_type,file_name,integrity_status,artifact_created_at FROM dr_backup_artifacts ORDER BY artifact_created_at DESC LIMIT 10;"'

dr-test:
	docker compose exec db sh -lc 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "INSERT INTO dr_requests(action,requested_by) VALUES ('"'"'restore_test'"'"','"'"'make:dr-test'"'"');"'

dr-replicate:
	docker compose exec db sh -lc 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "INSERT INTO dr_requests(action,requested_by) VALUES ('"'"'replicate'"'"','"'"'make:dr-replicate'"'"');"'
