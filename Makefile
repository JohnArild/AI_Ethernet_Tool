PYTHON ?= python3
export PYTHONPATH := src

.PHONY: test run-help profiles

test:
	$(PYTHON) -m unittest discover -s tests -t .

run-help:
	$(PYTHON) -m eit --help

profiles:
	$(PYTHON) -m eit --direct profiles
