.PHONY: web-smoke build clean

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".vite-temp" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info frontend/dist/ /tmp/openmanus_web_smoke_*
	docker builder prune -f 2>/dev/null || true

web-smoke:
	PYTHONDONTWRITEBYTECODE=1 ./scripts/local_web_smoke.sh

build:
	docker compose up -d --build
	docker builder prune -f
	@$(MAKE) clean
