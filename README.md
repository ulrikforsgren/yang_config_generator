# ned_config_creator #

  vhis is still an idea to test the concept of "automatically" create arbitrary device configuration from an NSO NED YANG model.

It consists of two parts:
 - pmod.py
   A pyang plugin to extract the required information from the YANG module(s) and store as a json structure.
   This is much dfaster to load than reparsing the modules every time.
   The extracted information is basically all structure containers, lists and leafs with datatypes and their restrictions e.g. lengths, ranges and patterns.
 - create_xml.py
   A script that loads a json schema file and creates arbitrary (random) configuration.
   It uses the rstr.xeger function to create strings from the patterns defined for the string datatypes and the ranges for numerical values.
   It is currently very limted and the ongoing work is mainly to identify the main issues of creating pure random data.


Limitations:
 - pmod.py:
   max-elements not handled.
   leafref not handled.
   instance-identifier datatype not handled.
   bits datatype not handled.
   when statements not handled.
 - create_xml.py:
   Unicode patterns used in some ieft string datatypes i.e \p{L} is replaced with a more restrictive pattern [a-zA-Z).
   Unicode patterns used in some ieft string datatypes i.e \p{N} is replaced with a more restrictive pattern [0-9).
   .* and .+ (dot) pattern is replaced with [a-z0-9]{0/1,15} to restrict the strings to be created.
   Number of list entries created is hardcoded to 1

To futher control creation and mitigate arised issues a possibility to use functions
at multiple levels have been added:
 - Generators for some datatypes e.g.: inet:ipv4-address, inet:ipv4-address, ...
 - Generators for network interface names
 - Generators for selected patterns that have caused creation of invalid strings.


Dependencies:
 - Tested with pyang version 2.5.2 from github.
 - NCS_DIR must be set to find dependent modules.


The cisco-ios-cli-6.77 YANG is currently included for development purposes.


Usage:

Build the json schema file: tailf-ned-cisco-ios.schema
> make


Generate config to be loaded into nso: ios.xml
> make ios.xml

