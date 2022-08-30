# Newest version of Pyang is required
export PYANGDIR=../pyang/bin/
export PYTHONPATH =../pyang

all:
	$(MAKE) tailf-ned-cisco-ios.json


tailf-ned-cisco-ios.json: tailf-ned-cisco-ios.yang\
			  cliparser-extensions-v11.yang

%.json-raw: %.yang
	$(PYANGDIR)pyang -p $(NCS_DIR)/src/ncs/yang\
	      --plugindir `pwd`/plugins -f pmod $< -o $@

%.json: %.json-raw
	cat $< | python3 -m json.tool - > $@
	rm $<

ios.xml: tailf-ned-cisco-ios.json
	python3 create_xml.py $< > raw
	cat raw | xmllint --pretty 1 - > $@
