.PHONY: adoc pdf clean backup-data

INVOICE ?= data/2026-04/invoice.json
PROFILE ?= data/profile.json
ITEMS ?= data/items.json


backup-data:
	./scripts/sync-data.sh
adoc:
	python3 generate_honorarnote.py --profile $(PROFILE) --items $(ITEMS) --invoice $(INVOICE)

pdf:
	python3 generate_honorarnote.py --profile $(PROFILE) --items $(ITEMS) --invoice $(INVOICE) --pdf
	$(MAKE) backup-data

clean:
	rm -rf build


