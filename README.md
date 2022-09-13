# yang_config_creator #

This is an idea to test the concept of (pseudo) randomly create arbitrary device configuration from YANG model.

Support for a lot of datatypes and variates are still missing and still only has a hard coded single list entry creation
algorithm/strategy.

The intention is to develop on a per use-case requirements basis, to stimulate features that are really
used and tested.

## Concept
The concept has been created from usability perspective to simplify the creation of arbitrary
configuration that can be controlled using parameters.

It should both to be possible to generate configuration from the schema using command line options without
the need of a descriptor file. Useful for generating small config snippets for "uncomplicated" YANG structures.

More complex YANG structures can be handled via a descriptor file that can be generated from the schema. Options
is used to control the generation in terms of selecting which part of the schema to select and which
algorithms and strategies to used for iterating lists, containers, leafs, ...

The basic flow of using a descriptor:
1. Compile YANG(s) --> JSON.
1. Analyze complexity.
1. Generate descriptor file.
1. Tweak descriptor file.
1. Generate config by running the descriptor file.

## Usage
### Generate schema file "router.json" from "router.yang"

Create a fast loading schema file in json format for the selected YANG modules. 

```make router.json```

### Analyze the complexity of the schema

Shows the complexity of the schema. This toolset is intended to help in the decision-making how to
generate the configuration. This is useful for both to be used with a descriptor file and without.

```./generate_config.py -m router.json complex```

### Generate descriptor file

Creates a descriptor file from the schema. Currently only with containers and lists with the key leafs names.

```./generate_config.py -m router.json gendesc > desc.py```

### Run the descriptor file

This currently only show that it is possible to iterate of the descriptor, but produces no config.

```./generate_config.py -m router.json rundesc desc.py```


## Priorities ##
* Generate XML output for command 'rundesc'
* Create initial test framework to secure an expected output.
* Support choice for command 'rundesc'
* Generate random values for leafs for command 'rundesc'
* Handle mandatory leafs

## Unprioritized
* Handle list key uniqueness
* Simple handling of generator functions
* Simple handling of variables and Python generators

## Contents ##
* pmod.py
  A pyang plugin to extract the required information from the YANG module(s) and store as a json structure.
  This is much dfaster to load than reparsing the modules every time.
  The extracted information is basically all structure containers, lists and leafs with datatypes and their restrictions e.g. lengths, ranges and patterns.
* generate_config.py
  A script that loads a json schema file and creates arbitrary (pseudo random) configuration.
  It uses the rstr.xeger function to create strings from the patterns defined for the string datatypes and the ranges for numerical values.
  It is currently very limted and the ongoing work is mainly to identify the main issues of creating pure random data.


## Limitations ##
* pmod.py:
    * min/max-elements not handled.
    * mandatory not handled.
    * instance-identifier datatype not handled.
    * bits datatype not handled.
    * when statements not handled.
    * Altered/complemented restrictions of user defined datatypes (typedefs) are
    not collected properly. Fortunately not very common...
* generate_config.py:
    * Unicode patterns used in some ieft string datatypes i.e \p{L} is replaced with a more restrictive pattern [a-zA-Z).
    * Unicode patterns used in some ieft string datatypes i.e \p{N} is replaced with a more restrictive pattern [0-9).
    * .* and .+ (dot) pattern is replaced with [a-z0-9]{0/1,15} to restrict the strings to be created.
    * Number of list entries created is hardcoded to 1

## Generator functions ##
To futher control creation and mitigate arised issues a possibility to use functions
at multiple levels have been added:
* Generators for some datatypes e.g.: inet:ipv4-address, inet:ipv4-address, ...
* Generators for network interface names
* Generators for selected patterns that have caused creation of invalid strings.


## Dependencies ##
* Tested with pyang version 2.5.x from github.
* NCS_DIR must be set to find dependent modules.


## Json schema format ##

The advantage of using pyang to pre-process the YANG modules and create a single
schema file that is to have a model that loads fast and is easy to traverse, with
the interesting information directly accessible. In this case the key leafs for
lists and datatypes of leafs and their restrictions.

The json format specification is found [here](schema-format-specification.md)

# Ideas #

## Descriptor file thoughts
- Different file structures
  - Only list entries
  - List entries and containers
  - Include key leaves
  - Include mandatory leaves
  - Include all leaves
  - ...
- Control statements 
  - __NO_INSTANCES
    - How many list entries to be created.
  - __LEAVES_ALGO
    - All/Percent/Random percent/...
  - __PROCESS_CONTAINERS
    - How process leaves in containers: Always/Random/No
  - ...


## Thoughts around config iteration algorithms and strategies
* Default algorithms and strategies should be used when creating config from the command line and
  and for unspecified nodes with no controlling statements in the descriptor file.
* The default algorithms and strategies should be possible to override to some degree from the
  command line.
* The default algorithms and strategies can be fully overridden using the descriptor file.

## Node evaluation thoughts

### lists
* Create 1 entry is default(?).
* Create n entries.
* Create a random number of entries.
* Override using generators in the descriptor file.

### Presence container
* Should a presence container to be handled like a singular list entry or as any other container
  as default.

### Mandatory leaves
* Always created by default.
* Override in descriptor file to not create (testing purposes)?

### Leaves
* All leaves are created by default(?)
* Create a subset of all leaves under e.g. root or list entry.
* Create a subset of all leaves under a container or list entry.

### Choices
* Select one random choice as default(?)

### Mandatory leafs
Should always be created.

### leafrefs and non-strict-leafrefs

Non-strict can be created without the need for it to point to an existing leaf.
Native leafrefs require an instance to exist.

What algorithm should be used?
 - Instances be created on the fly.
 - List entries should first be created. During a second pass leafrefs can be
   created to exising leafs.
 - Non-strict-leafsrefs can be created with both existing and non-existing
   instances.

### when statements

What algorithm should be used?
 - A first pass creating instances for all nodes without when statements. A
   second pass evaluates nodes with when statements and creates instances as
   the creation algorithm describes.

### must statements

Evaluating must statements can be tricky as they are an extention to individual
leafs restrictions and may reference multiple leafs.

What algorithm should be used?
 - Feature to easily list and show must expressions in model.
 - Possibility to create generator functions for containers 
