all:
	$(MAKE) tailf-ned-cisco-ios.json


tailf-ned-cisco-ios.json: tailf-ned-cisco-ios.yang\
			  cliparser-extensions-v11.yang

%.json: %.yang
	../pyang/bin/pyang --ignore-errors -p $(NCS_DIR)/src/ncs/yang\
	      --plugindir `pwd`/plugins -f pmod $< > raw.json
	cat raw.json | python3 -m json.tool - > $@
	#rm raw.json

ios.xml: tailf-ned-cisco-ios.json
	python3 create_xml.py $< > raw
	cat raw | xmllint --pretty 1 - > $@
