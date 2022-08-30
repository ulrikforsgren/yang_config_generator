# ned_config_creator #

This is still an idea to test the concept of "automatically" create arbitrary device configuration from an NSO NED YANG model.

## Priorities ##
* Compile multiple YANG modules into one json tree.
* Fix iteration so that passing schema information is transparent .
  Less complex, without the need to add new parameters.
* Fix the support for namespaces so that iteration and referencing leafs and
  typedefs works. Only very optimistic implementation today.


## TODO ##
* Possibility to generate config for selected parts of a YANG model.
* Support for when statements in some way, possibly using functions. Not sure
   if it is possible to do in a generalized way.
* Support for min/max-elements.
* Run tests to identify issues in various parts of the model.
* ???


## Contents ##
 * pmod.py
   A pyang plugin to extract the required information from the YANG module(s) and store as a json structure.
   This is much dfaster to load than reparsing the modules every time.
   The extracted information is basically all structure containers, lists and leafs with datatypes and their restrictions e.g. lengths, ranges and patterns.
 * create_xml.py
   A script that loads a json schema file and creates arbitrary (random) configuration.
   It uses the rstr.xeger function to create strings from the patterns defined for the string datatypes and the ranges for numerical values.
   It is currently very limted and the ongoing work is mainly to identify the main issues of creating pure random data.


## Limitations ##
* pmod.py:
    * min/max-elements not handled.
    * presence container not handled.
    * mandatory not handled.
    * instance-identifier datatype not handled.
    * bits datatype not handled.
    * when statements not handled.
    * Altered/complemented restrictions of user defined datatypes (typedefs) are
    not collected properly. Fortunately not very common...
* create_xml.py:
    * Unicode patterns used in some ieft string datatypes i.e \p{L} is replaced with a more restrictive pattern [a-zA-Z).
    * Unicode patterns used in some ieft string datatypes i.e \p{N} is replaced with a more restrictive pattern [0-9).
    * .* and .+ (dot) pattern is replaced with [a-z0-9]{0/1,15} to restrict the strings to be created.
    * Number of list entries created is hardcoded to 1
* Generic
    * Module prefixes are not handled in a unified way. It is present on to elements
      and some datatypes.

## Generator functions ##
To futher control creation and mitigate arised issues a possibility to use functions
at multiple levels have been added:
* Generators for some datatypes e.g.: inet:ipv4-address, inet:ipv4-address, ...
* Generators for network interface names
* Generators for selected patterns that have caused creation of invalid strings.


## Dependencies ##
* Tested with pyang version 2.5.2 from github.
* NCS_DIR must be set to find dependent modules.


The cisco-ios-cli-6.77 YANG is currently included for development purposes.


## Usage ##

Build the json schema file: tailf-ned-cisco-ios.json

    > make


Generate config to be loaded into nso under /devices/device{ce0}: ios.xml

    > make ios.xml

**NOTE!** It is not 100% guaranteed that all data will be accepted by NSO.


## Json schema format ##

The advantage of using pyang to pre-process the YANG modules and create a single
schema file that is to have a model that loads fast and is easy to traverse, with
the interesting information directly accessible. In this case the key leafs for
lists and datatypes of leafs and their restrictions.

The json format specification is found [here](schema-format-specification.md)

# Ideas #

## Evaluating leafrefs and non-strict-leafrefs

Non-strict can be created without the need for it to point to an existing leaf.
Native leafrefs require an instance to exist.

What algorithm should be used?
 - Instances be created on the fly.
 - List entries should first be created. During a second pass leafrefs can be
   created to exising leafs.
 - Non-strict-leafsrefs can be created with both existing and non-existing
   instances.

## Evaluating when statements

What algorithm should be used?
 - A first pass creating instances for all nodes without when statements. A
   second pass evaluates nodes with when statements and creates instances as
   the creation algorithm describes.

## Evaluating must statements

Evaluating must statements can be tricky as they are an extention to individual
leafs restrictions and may reference multiple leafs.

What algorithm should be used?
 - Feature to easily list and show must expressions in model.
 - Possibility to create generator functions for containers 
