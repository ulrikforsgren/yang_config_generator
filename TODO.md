# TODO

## List of unstructured things to do
 - Check descriptor file existence and print appropriate error message when not found or execution failure.
 - Check model file existence and print appropriate error message when not found.
 - How to generate string with multiple pattern statements?
 - invert-match not supported.

## Thoughts around datatypes
 - Handle min-elements/max-elements.
 - Support leaflists
 - What is default length for lmax, lmin

### Leafs
 - How should containers be processed: part of the leafs or separately
 - Handle mandatory leafs
 - Handle generator for a specific leaf
 - How to handle multiple patterns?

### Leafrefs
 - How should leafrefs be handled?
   Get a value if exists/create if not?
   Create anyway if non-strict ...
 - handle paths with paths inside [ ]
   ex: "/oc-if:interfaces/oc-if:interface[oc-if:name=current()/../interface]/oc-if:subinterfaces/
   oc-if:subinterface/oc-if:index"
 - leafref must point to an existing leaf
 - Create function that tracks the datatype that the leafref points to. 
   Needs to keep track of the current module when traversing back in the hierarchy

### Choices

#### Strategies how to handle choices
1. Add directives to descriptor file.
   - Choose one randomly
   - Override with directives/functions/generators
2. Explicitly specify node(s) from the case to be processed.
3. Implicit handling when not specified
   - Requires implicit handling of lists/presence containers/...


### Lists
 - Handle uniqueness of list keys

## Generate config
 - Arguments to specify limits (upper, lower) of instances to create
 - Regexp like matching to create generator for arbitrary part of the model?

## Complex analysis
 - Print note if leafref/when/must references outside --path.
 - Count instance-identifiers

## Namespaces/Prefixes
 - Handle namespaces/prefixes in a generic way. I.e. inherit the level above is not specified.

## Descriptor file generation

#### TODO
 * Add option for list/container and list strategies.
 * Add option for including choice meta nodes (if possible to exclude)
 * Add option for adding __NO_INSTANCES on lists and presence containers.
 * Add option for including key leafs.
 * Add option for including leafrefs.
 * Add option for including when/must comments
 *  - Comment if it references outside --path

Approaches to generate a descriptor:
 - Include every list, container and choice
 - No specification of number of list elements.
 - No leafs are specified.

Options:
 - Add default generators for key leafs (no specified --> use default generator)
 - Add all leafs

Options to add comments for:
 - List keys
 - Leafrefs
 - Must statements
 - When statements

Questions:
 - How to handle choices? 
 - Default is implicit?
 - Explicit specification

