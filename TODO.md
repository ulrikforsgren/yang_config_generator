TODO: List of unstructured things to do
 - How should leafrefs be handled?
   Get a value if exists/create if not?
   Create anyway if non-strict ...
 - Handle uniqueness of list keys
 - Refactor generate_random_data to take only node as input.
 - Should there be a default generator for each native type?
   To gets rid of the if mess...
   Easier to override types?!
 - Regexp like matching to create generator for arbitrary part of the model?
 - Handle min-elements/max-elements.
 - Arguments to specify limits (upper, lower) of instances to create

 - Handle namespaces/prefixes in a generic way. I.e. inherit the level above is not specified.
 - Handle choices (currently broken)

 - What is default length for lmax, lmin
 - leafref must point to an existing leaf
 - handle paths with paths inside [ ]
   ex: "/oc-if:interfaces/oc-if:interface[oc-if:name=current()/../interface]/oc-if:subinterfaces/
   oc-if:subinterface/oc-if:index"
 - Create function that tracks the datatype that the leafref points to. 
   Needs to keep track of the current module when traversing back in the hierarchy
 - How to handle multiple patterns?
   Is generators the only option?
 - Handle generator for a specific leaf
 - Print note if leafref/when/must references outside --path.
 - Check descriptor file existence and print appropriate error message when not found or execution failure.
 - Handle mandatory leafs
 - Check model file existence and print appropriate error message when not found.
 - How should containers be processed: part of the leafs or separately
