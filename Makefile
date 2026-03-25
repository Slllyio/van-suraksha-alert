.PHONY: help setup train dashboard deploy test lint clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv and install dependencies
	python -m venv .venv
	.venv/Scripts/activate && pip install -r requirements.txt

download-data:  ## Download HLS imagery + FIRMS + ancillary data from GEE
	python scripts/download_all_years.py
	python scripts/download_firms_historical.py
	python scripts/download_ancillary_expanded.py

train-lgbm:  ## Train LightGBM fire classification model
	python scripts/launch_training.py --task classify

train-vanaagni:  ## Train VanAagni neural fire detector
	python src/train/train.py --config config.yaml --task detect

dashboard:  ## Launch Streamlit dashboard
	streamlit run dashboard/app.py --server.port 8501

pipeline:  ## Run NRT alert pipeline (single pass)
	python scripts/run_pipeline.py --task all

scheduler:  ## Start daily EWS scheduler daemon
	python scripts/ews_scheduler.py

test:  ## Run test suite
	python -m pytest tests/ -v --tb=short

lint:  ## Run linting
	python -m ruff check src/ scripts/
	python -m pyright src/

clean:  ## Remove temporary files and caches
	rm -rf tmp/ cache/ __pycache__/ .pytest_cache/
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
