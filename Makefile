# Pyang version 2.5.x or newer is required
export PYANGDIR=../pyang/bin/
export PYTHONPATH=../pyang

ifeq ($(shell test -x $(PYANGDIR)pyang; echo $$?),1)
  $(error pyang not found. Get pyang 2.5.x or newer and update PYANGDIR in Makefile)
endif

PYANG_VERSION=$(shell PYTHONPATH=$(PYTHONPATH) $(PYANGDIR)pyang -v | cut -f2 -d' ')
PYANG_VER_MAJ=$(shell echo $(PYANG_VERSION) | cut -f1 -d.)
PYANG_VER_MIN=$(shell echo $(PYANG_VERSION) | cut -f2 -d.)

# Test required pyang version
ifeq ($(shell test $(PYANG_VER_MAJ) -lt 2; echo $$?),0)
  $(error pyang version 2.5.x or newer is required)
endif
ifeq ($(shell test $(PYANG_VER_MIN) -lt 5; echo $$?),0)
  $(error pyang version 2.5.x or newer is required)
endif

PYANGOPTIONS=
#PYANGOPTIONS=--ignore-errors

all:
	$(MAKE) tailf-ned-cisco-ios.json


tailf-ned-cisco-ios.json: tailf-ned-cisco-ios.yang\
			  cliparser-extensions-v11.yang

%.json-raw: %.yang
	$(PYANGDIR)pyang -p $(NCS_DIR)/src/ncs/yang\
	     $(PYANGOPTIONS)\
	      --plugindir `pwd`/plugins -f pmod $< -o $@

ab.json-raw: a.yang b.yang
	$(PYANGDIR)pyang -p $(NCS_DIR)/src/ncs/yang\
	      --plugindir `pwd`/plugins -f pmod $^ -o $@

%.json: %.json-raw
	cat $< | python3 -m json.tool - > $@
	rm $<

ios.xml: tailf-ned-cisco-ios.json
	python3 create_xml.py $< > raw
	cat raw | xmllint --pretty 1 - > $@
