install:
	install -m755 coldcore /usr/local/bin/coldcore

docker-build:
	docker build --tag coldcore/test .

test: docker-build
	docker run -v $$(pwd)/coldcore:/coldcore/coldcore.py:ro -e PYTHONPATH=/coldcore \
		-v $$(pwd):/src:ro coldcore/test pytest -vv --color=yes test/

lint: docker-build
	docker run --rm -v $$(pwd):/src:ro coldcore/test flake8 coldcore
	docker run --rm -v $$(pwd):/src:ro coldcore/test black --check coldcore
	docker run --rm -v $$(pwd):/src:ro coldcore/test mypy coldcore

.PHONY: docker-build lint test
