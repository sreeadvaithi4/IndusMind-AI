.PHONY: build up down logs test migrate setup shell createsuperuser

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f web

test:
	cd backend && python manage.py test -v 1

migrate:
	docker compose exec web python manage.py migrate

setup: build up migrate
	@echo "✓ IndusMind AI is running at http://localhost:8000"
	@echo "  Create an admin user: docker compose exec web python manage.py createsuperuser"

shell:
	docker compose exec web python manage.py shell

createsuperuser:
	docker compose exec web python manage.py createsuperuser

# Local development (without Docker)
dev:
	cd backend && python manage.py runserver

dev-test:
	cd backend && python manage.py test -v 1

dev-migrate:
	cd backend && python manage.py migrate
