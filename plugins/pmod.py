"""pmod output plugin

This plugin takes a YANG data model and produces a JSON driver file
that can be used by the *json2xml* script for translating a valid JSON
configuration or state data to XML.

Requires the latest version of pyang from github.

Missing YANG information (not passed to json):
 - mandatory
 - when
 - leafref

Special trix to generate config:
 - Escaping all xml strings
 - Replacing .* and .+ in all regexps.
 - Replacing XSD specific unicode patterns with generic versions.
 - Generic string limitation to 255 characters.
 - Removing zone pattern (%[\p{N}\p{L}]+)? from inet address patterns.
"""

# TODO:
#  - Handle additional restrictions on derived types.
#    Low prio, probably fairly seldom used.
#  - Handle modules namespaces in a consistent way.
#    Module is not separated for typedefs.
#    Type in the local module can be used with and without prefix.
#    No support for combining modules in the same tree.
#  - Maintain a local copy of xeger to control generation e.g.:
#    - string length limits
#    - What is included in the . and ? sets etc.
#  - Should typedef type be handled in a generic way?
#  - Return the array of ranges for decimal64.

import json

from pyang import plugin, error, types, statements
from pyang.util import unique_prefixes
import pprint as pp
pprint = pp.PrettyPrinter(indent=4).pprint


#
# Function to replace a pattern within a regexp.
# Outside brachets [] they must be added.
# NOTE! This function does not take care of all combinations.
#
def replace_in_regexp(s, f, r):
  while (i:=s.find(f)) != -1:
    lb = s.rfind(r'[', 0, i)
    rb = s.rfind(r']', 0, i)
    if lb<=rb:
      s = s.replace(f, f'[{r}]', 1)
    else:
      s = s.replace(f, r, 1)
  return s

def replace_patterns(p):
  # Remove support for zone after ipv4/6 adresses
  p = p.replace("(%[\p{N}\p{L}]+)?", "")
  # Replace unicode patterns...
  if r'\p{N}' in p:
    p = replace_in_regexp(p, r'\p{N}', r'0-9')
  if r'\p{L}' in p:
    p = replace_in_regexp(p, r'\p{L}', r'a-zA-Z')
  return p

def flatten_union(lst):
  for i in lst:
    if i is None:
        continue
    t,p = i
    if t == 'union':
      for t2, p2 in flatten_union(p):
        yield t2, p2
    else:
      yield t,p

def unique_types(lst):
    ulst = []
    for t in lst:
        if t not in ulst:
            ulst.append(t)
    return ulst


def pyang_plugin_init():
    plugin.register_plugin(PModPlugin())

class PModPlugin(plugin.PyangPlugin):
    def add_output_format(self, fmts):
        self.multiple_modules = True
        fmts['pmod'] = self

    def setup_fmt(self, ctx):
        ctx.implicit_errors = False

    def emit(self, ctx, modules, fd):
        """Main control function.
        """
        for epos, etag, eargs in ctx.errors:
            if error.is_error(error.err_level(etag)):
                raise error.EmitError("PMod plugin needs a valid module")
        tree = {}
        mods = {}
        annots = {}
        self.typedefs = {}
        self.identities = {}
        for m,p in unique_prefixes(ctx).items():
            mods[m.i_modulename] = [p, m.search_one("namespace").arg]
        for module in modules:
            for ann in module.search(("ietf-yang-metadata", "annotation")):
                typ = ann.search_one("type")
                annots[module.arg + ":" + ann.arg] = (
                    "string" if typ is None else self.base_type(ann, typ))
        #print("-"*80)
        for module in modules:
            for i,st in module.i_identities.items():
                for b in st.search("base"):
                    if b.arg not in self.identities:
                        self.identities[b.arg] = []
                    self.identities[b.arg].append(i)
                self.identities[i] = []
        for i in self.identities:
            for sub in self.identities[i].copy():
                if sub in self.identities:
                    self.identities[i] += self.identities[sub]

        for module in modules:
            self.process_children(module, tree, None)
        json.dump({
            "modules": mods,
            "tree": tree,
            "typedefs": self.typedefs,
            "identities": self.identities,
            "annotations": annots
            }, fd)
        #pprint(tree)

    def process_children(self, node, parent, pmod):
        """Process all children of `node`, except "rpc", "action" and "notification".
        """
        for ch in node.i_children:
            if ch.keyword in ["rpc", "notification", ('tailf-common', 'action')]:
                continue
            if ch.keyword in ["case"]:
                ndata = {}
                parent[ch.arg] = ndata
                self.process_children(ch, ndata, pmod)
                continue
            if ch.i_module.i_modulename == pmod:
                nmod = pmod
                nodename = ch.arg
            else:
                nmod = ch.i_module.i_modulename
                nodename = "%s:%s" % (nmod, ch.arg)
            ndata = [ch.keyword]
            if ch.keyword == "container":
                ndata.append({})
                self.process_children(ch, ndata[1], nmod)
            elif ch.keyword == "list":
                ndata.append({})
                self.process_children(ch, ndata[1], nmod)
                ndata.append([(k.i_module.i_modulename, k.arg)
                              for k in ch.i_key])
            elif ch.keyword in ["leaf", "leaf-list"]:
                st = ch.search_one("type")
                dt = self.type_data(st)
                if dt is None:
                    continue
                nst = ch.search_one(('tailf-common','non-strict-leafref'))
                if nst:
                    path = nst.search_one('path')
                    dt = ('ns-leafref', path.arg)
                elif dt[0] == 'union':
                    flat_union = [ m for m in flatten_union(dt[1]) ]
                    dt = ('union', unique_types(flat_union))
                ndata.append(dt)
            elif ch.keyword in ["choice"]:
                ndata.append({})
                self.process_children(ch, ndata[1], pmod)
            modname = ch.i_module.i_modulename
            parent[nodename] = ndata

    def base_type(self, ch, of_type):
        """Return the base type of `of_type`."""
        while 1:
            if of_type.arg == "leafref":
                if of_type.i_module.i_version == "1":
                    node = of_type.i_type_spec.i_target_node
                else:
                    node = ch.i_leafref.i_target_node
            elif of_type.i_typedef is None:
                break
            else:
                node = of_type.i_typedef
            of_type = node.search_one("type")
        if of_type.arg == "decimal64":
            return [of_type.arg, int(of_type.search_one("fraction-digits").arg)]
        elif of_type.arg == "union":
            return [of_type.arg, [self.base_type(ch, x) for x in of_type.i_type_spec.types]]
        else:
            return of_type.arg


    def type_data(self, t):
        #print("-"*80)
        #print(1, t)
        #print(1.1, type(t.i_typedef))
        #print(6, type(t.i_type_spec))
        #if isinstance(t.i_type_spec, types.LengthTypeSpec):
        #  print(6.1, t.i_type_spec.lengths)
        #elif isinstance(t.i_type_spec, types.PatternTypeSpec):
        #  print(6.2, t.i_type_spec.res)
        #  if isinstance(t.i_type_spec.base, LengthTypeSpec):
        #    print(6.3, t.i_type_spec.base.lengths)
        #  else:
        #    print(6.4, t.i_type_spec.base.lengths)
        #print(7.1, type(t.i_typedefs))
        #print(7.2, t.i_typedefs)
        #print(8, t.i_is_validated)
        #print(9, t.substmts)
        if t.i_typedef: # Handle references to typedefs
            td = self.type_data(t.i_typedef.substmts[0])
            #print(f"X {t}", end='')
            #pprint(td)
            self.add_typedef(t, td)
            return ('typedef', t.arg)
        ts = t.i_type_spec # Is it better to use the type name instead?
        n = ts.name
        if n in ['uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64']:
            if isinstance(ts, types.RangeTypeSpec):
              ranges = ts.ranges
              #print(t.substmts)
              rst = t.search_one('range')
              sst = rst.search_one(('tailf-common', 'step'))
              if sst:
                step = int(sst.arg)
                ranges = [r+(step,) for r in ranges]
            else:
              ranges = []
            rt = (n, ranges)
        elif n == 'decimal64':
            # TODO: Return the array of ranges
            range = (float(str(ts.min)), float(str(ts.max))) if len(t.i_ranges) else None
            fd = ts.fraction_digits
            rt = (n, (fd, range))
        elif n == 'empty':
            rt = (n, None)
        elif n == 'boolean':
            rt = (n, None)
        elif n == 'string':
            bts = ts
            if isinstance(bts, types.PatternTypeSpec):
                patterns = bts.res
                patterns = [ replace_patterns(str(p)) for p in ts.res ]
                bts = ts.base
            else:
                patterns = []
            if isinstance(bts, types.LengthTypeSpec):
                lengths = bts.lengths
            else:
                lengths = []
            rt = (ts.name, (lengths, patterns))
        elif n == 'enumeration':
            rt = (n, [e for e,_ in ts.enums])
        elif n == 'union':
            # Resolves nested unions and returns
            # and returns a flattened union 
            ta = []
            if t.i_typedef:
                ut = t.i_typedef.search_one('type')
            else:
                ut = t
            subtypes = ut.search("type")
            for st in subtypes:
                ta.append(self.type_data(st))
            rt = (ts.name, ta)
        elif n == 'leafref':
            path = t.search_one('path')
            rt = (ts.name, path.arg)
        elif n == 'identityref':
            base = t.search_one('base')
            rt = (ts.name, base.arg)
        elif n == 'binary':
            return None
        else:
            raise TypeError(f"Can't handle type: {t.arg} {n}")
        return rt

    def add_typedef(self, t, rt):
        if t.arg in self.typedefs:
            return
        self.typedefs[t.arg] = rt
