.PHONY: run test eval check-llm

run:
	python manage.py run

test:
	python manage.py test

eval:
	python manage.py eval --cases $(CASES)

check-llm:
	python manage.py check-llm
