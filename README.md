# ned_config_creator #

This is still an idea to test the concept of "automatically" create arbitrary device configuration from an NSO NED YANG model.

## TODO ##
 - Possibility to generate config for selected parts of a YANG model.
 - Support for when statements in some way, possibly using functions. Not sure
   if it is possible to do in a generalized way.
 - Support for max-elements.
 - Run tests to identify issues in various parts of the model.
 - ???


## Contents ##
 - pmod.py
   A pyang plugin to extract the required information from the YANG module(s) and store as a json structure.
   This is much dfaster to load than reparsing the modules every time.
   The extracted information is basically all structure containers, lists and leafs with datatypes and their restrictions e.g. lengths, ranges and patterns.
 - create_xml.py
   A script that loads a json schema file and creates arbitrary (random) configuration.
   It uses the rstr.xeger function to create strings from the patterns defined for the string datatypes and the ranges for numerical values.
   It is currently very limted and the ongoing work is mainly to identify the main issues of creating pure random data.


## Limitations ##
 - pmod.py:
  - max-elements not handled.
  - leafref not handled.
  - instance-identifier datatype not handled.
  - bits datatype not handled.
  - when statements not handled.
  - Altered/complemented restrictions of user defined datatypes (typedefs) are
    not collected properly. Fortunately not very common...
 - create_xml.py:
  - Unicode patterns used in some ieft string datatypes i.e \p{L} is replaced with a more restrictive pattern [a-zA-Z).
  - Unicode patterns used in some ieft string datatypes i.e \p{N} is replaced with a more restrictive pattern [0-9).
  - .* and .+ (dot) pattern is replaced with [a-z0-9]{0/1,15} to restrict the strings to be created.
  - Number of list entries created is hardcoded to 1
 - Generic
  - Module prefixes are not handled in a unified way. It is present on to elements
    and some datatypes.
To futher control creation and mitigate arised issues a possibility to use functions
at multiple levels have been added:
 - Generators for some datatypes e.g.: inet:ipv4-address, inet:ipv4-address, ...
 - Generators for network interface names
 - Generators for selected patterns that have caused creation of invalid strings.


## Dependencies ##
 - Tested with pyang version 2.5.2 from github.
 - NCS_DIR must be set to find dependent modules.


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

pmpd.py is decending from standard jstree.py plugin.

    {
        "modules": {
            ...
        },
        "tree": {
            ...
        },
        "typedefs": {
            ...
        },
        "annotations": {}
    }

## Element encoding ##


**Container**

    "trigger": [
         "container",
         {
            # Members...
         }
    ]


**List**

    "ip": [
        "list",
        {
            # Members...
        },
        [ # Key leafs (list of tuples with module and leaf name)
            [ "tailf-ned-cisco-ios", "divert-code" ]
        ]
    ]

**Leaf**

    "rate": [
        "leaf",
        [
            "uint16", # Datatype
            []        # Type specific restrictions
        ]
    ],

## Datatype encoding ##

### numerical types ###

**integers**

    [
        "uint16",
        [
            [ # Ranges
                0,
                7
            ]
            # May contain zero or more ranges
        ]
    ]

**decimal64**

    [
        "decimal64",
        [
            1, # Fraction digits
            [ # Ranges
                0.0,
                8.0
            ]
            # May contain zero or more ranges
        ]
    ]


***Enumerations**

    [
        "enumeration",
        [
            "eq",
            "ge",
            "gt",
            "le",
            "lt",
            "ne"
        ]
    ]


**strings**

    [
        "string",
        [
            [ # Lengths
                [
                    5,
                    10
                ]
                # May contain zero of more lengths
            ],
            [ # Patterns
                "[0-9a-fA-F]{1,6}:[0-9a-fA-F]{1,8}"
                # May contain zero of more lengths
            ]
        ]
    ]

**non-strict leafref**

    [
        "ns-leafref",
        "../../../../../cable/downstream-pilot-tone/profile/id"
    ]

**Empty leafs**

    [
        "empty",
        null
    ]
