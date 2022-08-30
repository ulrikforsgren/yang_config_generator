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
        "identities": {
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

**leafref**

    [
        "leafref",
        "../../key/name"
    ]

**Empty leafs**

    [
        "empty",
        null
    ]
