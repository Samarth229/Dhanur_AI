.PHONY: run test eval check-llm retrieve quote chat

run:
	python manage.py run

test:
	python manage.py test

eval:
	python manage.py eval --cases $(CASES)

check-llm:
	python manage.py check-llm

retrieve:
	python manage.py retrieve "$(MESSAGE)"

quote:
	python manage.py quote --item "$(ITEM)" --distance "$(DISTANCE)"

chat:
	python manage.py chat
