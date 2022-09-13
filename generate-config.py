#!/usr/bin/env python3

from argparse import ArgumentParser, RawDescriptionHelpFormatter
import json
import random
import sys
from xml.dom import minidom
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import rstr


def prettify(elem):
    """Return a pretty-printed XML string for the Element.
    """
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


# TODO: List of things to do
#  - How should leafrefs be handled?
#    Get a value if exists/create if not?
#    Create anyway if non-strict ...
#  - Handle uniqueness of list keys
#  - Refactor generate_random_data to take only node as input.
#  - Should there be a default generator for each native type?
#    To gets rid of the if mess...
#    Easier to override types?!
#  - Regexp like matching to create generator for arbitrary part of the model?
#  - Handle min-elements/max-elements.


####################################################################
#  Argument Parser
####################################################################

def create_parser():
    p = ArgumentParser(
        formatter_class=RawDescriptionHelpFormatter,
    )
    p.add_argument("-m", "--model",
                        action='store',
                        dest='model',
                        default='model.json',
                        help="JSON schema model (default=model.json)")
    p.add_argument("-p", "--path",
                        type=str,
                        help="Select model branch to process")
    p.add_argument("--verbose",
                        action='store_true',
                        default=False,
                        help="Enable verbose mode")
    return p, p.add_subparsers(dest="subcommand")


def set_epilog(parser, subparsers):
    l = [(f"{n} {s}",h) for n,s,h in subparsers.cmds]
    maxl = max(len(s) for s,_ in l)
    import textwrap
    parser.epilog = textwrap.dedent(
        "commands arguments: (-h for details)\n"+
        "\n".join([f"  {s:<{maxl}}   {h}" for s,h in l]))


parser, subparsers = create_parser()


def argument(*name_or_flags, **kwargs):
    return 'a', list(name_or_flags), kwargs


def mutex(arguments, **kwargs):
    return 'm', arguments, kwargs


def subcommand(arguments=[], help='', parent=subparsers):
    if not hasattr(parent, 'cmds'): parent.cmds = []

    def decorator(func):
        name = func.__name__[4:]
        parser = parent.add_parser(name, description=func.__doc__)
        for t, args, kwargs in arguments:
            if t == 'a':
                parser.add_argument(*args, **kwargs)
            elif t == 'm':
                g = parser.add_mutually_exclusive_group(**kwargs)
                for _, a, kw in args:
                    g.add_argument(*a, **kw)
        parser.set_defaults(func=func)

        def strip_prefix(s):
            return s[len(parser.prog) + 8:].rstrip()

        parent.cmds.append((name, strip_prefix(parser.format_usage()),
                            help))

    return decorator


def kp2str(kp, starting_slash=True):
    def mod_colon_name(e):
        m, n = e
        if m is not None:
            return f'{m}:{n}'
        return n
    mcn = map(mod_colon_name, kp)
    path = '/'.join(mcn)
    if starting_slash:
        path = '/' + path
    return path


def str2kp(path):
    # path must always start with /
    parts = path.split('/')
    assert(parts[0] == '')
    kp = []
    for part in parts[1:]:
        p = part.split(':')
        if len(p) == 1:
            kp.append((None, p[0]))
        else:
            kp.append((p[0], p[1]))
    return kp


#############################################################################################################
# Schema
#############################################################################################################
# TODO: Handle namespaces/prefixes in a generic way. I.e. inherit the level above is not specified.
# TODO: Handle choices (currently broken)
def find_path(schema, path, kp=None):
    # path is assumed to be well formatted, starting with a single /
    kp = kp or str2kp(path)
    (module, name) = kp[0]
    for ch in schema.children.values():
        if name == ch.name:
            if module is False or module == ch.module:
                if len(kp) == 1:
                    return ch
                return find_path(ch, path, kp[1:])
    return None


def find_kp(ch, kp):
    for p in kp:
        ch = ch.find(p)
        if ch is None:
            return None
    return ch


def get_ns(m, schema):
    return schema['modules'][m][1]


class Node:
    def __init__(self, parent, name, module=None, wm=None):
        self.parent = parent
        self.name = name
        self.module = module
        self.when = ''
        self.must = ''  # Not all nodes have support for must, but it will be validated by pyang and empty for those.
        if wm is not None:
            self.when, self.must = wm

    @property
    def get_kp(self):
        kp = []
        node = self
        while isinstance(node, Node):
            kp = [(node.module, node.name)] + kp
            node = node.parent
        return tuple(kp)

    def get_kp2level(self):
        node = self
        kp = [(node.module, node.name)]
        node = node.parent
        while not isinstance(node, Schema) and not isinstance(node, List):
            kp = [(node.module, node.name)] + kp
            node = node.parent
        return tuple(kp)


class HasChildren:
    def __init__(self):
        self.children = {}

    def __iter__(self):
        for k, v in self.children.items():
            yield k, v

    def find(self, p):
        module, name = p
        for ch in self.children.values():
            if isinstance(ch, Choice):
                ch = ch.find(p)
                if ch is not None:
                    return ch
            elif name == ch.name and (module is None or module == ch.module):
                return ch
        return None

    def find_path(self, p):
        m = None
        n = p
        if ':' in p:
            m, n = p.split(':')
        return self.find((m, n))


class Container(Node, HasChildren):
    def __init__(self, parent, name, module=None, presence=False, wm=None):
        Node.__init__(self, parent, name, module, wm)
        HasChildren.__init__(self)
        self.presence = presence


class Choice(Node):
    def __init__(self, parent, name, wm=None):
        super().__init__(parent, name, wm=wm)
        self.choices = {}

    def __iter__(self):
        for k, v in self.choices.items():
            yield k, v

    def __len__(self):
        return len(self.choices)

    def __getitem__(self, n):
        return self.choices[n]

    def find(self, p):
        module, name = p
        for case in self.choices.values():
            for _, ch in case.items():
                if isinstance(ch, Choice):
                    ch = ch.find(p)
                    if ch is not None:
                        return ch
                elif name == ch.name and (module is None or module == ch.module):
                    return ch
        return None


class List(Node, HasChildren):
    def __init__(self, parent, name, key_leafs, module=None, wm=None):
        Node.__init__(self, parent, name, module, wm)
        HasChildren.__init__(self)
        self.key_leafs = [kl[1] for kl in key_leafs]
        self.nk_children = {}  # Non key children


class Leaf(Node):
    def __init__(self, parent, name, datatype, module=None, wm=None):
        super().__init__(parent, name, module, wm)
        self.datatype = datatype


class LeafList(Leaf):
    pass


class Schema(HasChildren):
    def __init__(self, schema=None):
        super().__init__()
        self.json = schema
        if schema is not None:
            load_schema(schema['tree'], self)
        self.name = ''
        self.module = ''

    def prefix2module(self, prefix):
        for m_name, (m_prefix, m_ns) in self.json['modules'].items():
            if prefix == m_prefix:
                return m_name
        return None

    @property
    def get_kp(self):
        return []


def load_schema(schema, node, children=None, parent=None):
    children = children if children is not None else node.children
    parent = parent or node
    for k, v in schema.items():
        m = None
        mk = k
        if ':' in k:
            m, k = k.split(':')
        t, wm, dt, *r = v
        if t in ['container', 'p-container']:
            nn = Container(parent, k, module=m, presence=t == 'p-container', wm=wm)
            load_schema(dt, nn)
        elif t == 'list':
            nn = List(parent, k, r[0], m, wm=wm)
            load_schema(dt, nn)
            for c, v2 in nn.children.items():
                if c not in nn.key_leafs:
                    nn.nk_children[c] = v2
        elif t == 'choice':
            nn = Choice(parent, k, wm=wm)
            for case, v2 in dt.items():
                c = {}
                nn.choices[case] = c
                load_schema(v2, nn, parent=parent, children=c)
        elif t == 'leaf':
            nn = Leaf(parent, k, dt, m, wm=wm)
        elif t == 'leaf-list':
            nn = LeafList(parent, k, dt, m, wm=wm)
        else:
            raise Exception(f'Unhandled type {t}')
        if nn is not None:
            children[mk] = nn


#############################################################################################################
# Helper function for generating random config
#############################################################################################################
def compile_keypath_generators(d):
    g = {}
    for k, v in d.items():
        assert (k[0] == '/')
        kp = k.split('/')[1:]
        g[tuple(kp)] = v
    return g


def string_generator(_datatype):
    return rstr.xeger("[a-z][a-z0-9_-]+")


def ulrik_generator(_datatype):
    return rstr.xeger("[uU][lL][rR][iI][kK]")


def ipv4_generator(_datatype):
    return '{}.{}.{}.{}'.format(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255),
                                random.randint(0, 255))


def ipv4_prefix_generator(_datatype):
    return '{}.{}.{}.{}/{}'.format(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255),
                                   random.randint(0, 255), random.randint(1, 32))


def ipv6_generator(_datatype):
    return '{:04X}:{:04X}::{:02X}'.format(random.randint(0, 65535), random.randint(0, 65535), random.randint(0, 255))


def ipv6_prefix_generator(_datatype):
    return '{:04X}:{:04X}::{:02X}/{}'.format(random.randint(0, 65535), random.randint(0, 65535), random.randint(0, 255),
                                             random.randint(0, 127))


def rd_generator(_datatype):
    return '{}:{}'.format(random.randint(0, 65535), random.randint(0, 255))


def uint16_generator(_datatype):
    return str(random.randint(0, 511))


def uint16sub_generator(_datatype):
    return '{}.{}'.format(random.randint(0, 511), random.randint(0, 128))


def eth_generator(_datatype):
    return '{}/{}'.format(random.randint(0, 66), random.randint(0, 128))


def permit_expr_generator(_datatype):
    """
  ((internet)|(local-AS)|(no-advertise)|(no-export)|(\\d+:\\d+)|(\\d+))( (internet)|(local-AS)|(no-advertise)|
  (no-export)|(\\d+:\\d+)|(\\d+))*
    """
    # TODO: Create function from the regexp above...
    return 'internet'


def permit_generator(_datatype):
    return rstr.xeger("(permit|deny|remark) [a-z ]{5-15}")


def acl_generator(_datatype):
    return rstr.xeger(
        "(permit [a-z ]{5,15})|(deny [a-z ]{5,15})|(remark [a-z ]{5,15})|([0-9]+)|(dynamic [a-z ]{5,15})|"
        "(evaluate [a-z ]{5,15})")


def acl2_generator(_datatype):
    return rstr.xeger("(permit [a-z ]{5,15})|(deny [a-z ]{5,15})|(remark [a-z ]{5,15})|([0-9]+)|(dynamic [a-z ]{5,15})")


def hex_generator(_datatype):
    return rstr.xeger("[a-fA-F0-9]*")


def aaa_name_generator(_datatype):
    return rstr.xeger("(default)|([a-z_]{5,15})")


datatype_generators = {
    #  'string': string_generator,
    #  't1': ulrik_generator,
    'inet:ipv4-address': ipv4_generator,
    'ios:ipv4-prefix': ipv4_prefix_generator,
    'inet:host': ipv4_generator,
    'inet:ipv6-address': ipv6_generator,
    'ios-ipv6-address': ipv6_generator,
    'ipv6-prefix': ipv6_prefix_generator,
    'ios:ipv6-prefix': ipv6_prefix_generator,
    'rd-type': rd_generator,
    'asn-ip-type': rd_generator,
    'aaa-authentication-name-type': aaa_name_generator,
    'aaa-authorization-name-type': aaa_name_generator,
}

keypath_generators = compile_keypath_generators({
    '/interface/Port-channel': uint16_generator,
    '/interface/Port-channel-subinterface/Serial': uint16sub_generator,
    '/interface/Serial': uint16_generator,
    '/interface/Serial-subinterface/Serial': uint16sub_generator,
    '/interface/Cable': uint16_generator,
    '/interface/Modular-Cable': uint16_generator,
    '/interface/Wideband-Cable': uint16_generator,
    '/interface/Cellular': uint16_generator,
    '/interface/Embedded-Service-Engine': uint16_generator,
    '/interface/Ethernet': eth_generator,
    '/interface/FastEthernet': eth_generator,
    '/interface/TenGigabitEthernet': eth_generator,
    '/ip/ftp/password/password-container/password': string_generator,
    '/ip/prefix-list/prefixes': string_generator,
})

pattern_generators = {
    "((internet)|(local-AS)|(no-advertise)|(no-export)|(\\d+:\\d+)|(\\d+))( (internet)|(local-AS)|(no-advertise)|"
    "(no-export)|(\\d+:\\d+)|(\\d+))*": permit_expr_generator,
    "((internet)|(local\\-AS)|(no\\-advertise)|(no\\-export)|(\\d+:\\d+)|(\\d+))( (internet)|(local\\-AS)|"
    "(no\\-advertise)|(no\\-export)|(\\d+:\\d+)|(\\d+))*": permit_expr_generator,
    "(permit.*)|(deny.*)|(remark.*)": permit_generator,
    "[a-fA-F0-9].*": hex_generator,
    "(permit .*)|(deny .*)|(remark .*)|([0-9]+.*)|(dynamic .*)|(evaluate .*)": acl_generator,
    "(permit.*)|(deny.*)|(remark.*)|(dynamic.*)": acl2_generator,
}

ilimits = {
    'uint8': (0, 255),
    'uint16': (0, 65535),
    'uint32': (0, 4294967295),
    'uint64': (0, 18446744073709551615),
    'int8': (-128, 127),
    'int16': (-32768, 32767),
    'int32': (-2147483648, 2147483647),
    'int64': (-9223372036854775808, 9223372036854775807),
}


def generate_random_data(datatype, schema, module, node):
    identities = schema.json['identities']
    typedefs = schema.json['typedefs']
    dt, r = datatype

    if dt == 'union':
        # Select one random datatype in the union
        dt, r = random.choice(r)

    g = datatype_generators.get(dt)
    if g:
        return g(datatype)

    if dt == 'empty':
        return None
    elif dt == 'string':
        lengths, patterns = r
        if patterns:
            # TODO: How to handle multiple patterns?
            #       Is generators the only option?
            pattern = patterns[0]
        else:
            pattern = "[a-zA-Z0-9 ._]+"
        if lengths:
            length = random.choice(lengths)  # Select a random length
            lmin, lmax = length
            lmax = lmax or lmin
        else:
            # TODO: What is default length
            lmin, lmax = 1, 255
        v = ""
        x = 0
        g = pattern_generators.get(pattern)
        # Avoid generating strings with 'non-readable' or 'invalid' chars.
        if '.*' in pattern:
            pattern = pattern.replace('.*', '[a-z0-9]{0,15}')
        if '.+' in pattern:
            pattern = pattern.replace('.+', '[a-z0-9]{1,15}')
        while len(v) < lmin:  # Iterate until we get a string that is long enough
            # ps = pattern.split('|')
            # print(ps)
            if g:
                v = g(datatype)
            else:
                v = rstr.xeger(pattern)
            x += 1
            if x == 100:
                print(pattern)
                print(lmin, lmax)
        v = escape(v)
        v = v.replace(chr(11), "")
        v = v.replace(chr(12), "")
        if lmax and len(v) > lmax:
            return v[:lmax]
        return v
    elif dt == 'boolean':
        return str(bool(random.randint(0, 1))).lower()
    elif dt in ['uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64']:
        if not r:
            mi, mx = ilimits[dt]
            step = 1
        else:
            r = random.choice(r)
            mi, mx, *step = r
            step = step[0] if step else 1
            if mx is None:
                mx = mi
        if mi == 'min':
            mi = ilimits[dt][0]
        elif mi == 'max':
            mi = ilimits[dt][1]
        if mx == 'min':
            mx = ilimits[dt][0]
        elif mx == 'max':
            mx = ilimits[dt][1]
        return str(random.randrange(mi, mx + 1, step))
    elif dt == 'enumeration':
        return random.choice(r)
    elif dt == 'decimal64':
        fd, r = r  # Get fraction digits and optional range
        if not r:
            n = str(random.randint(-9223372036854775808, 9223372036854775807))
        else:
            mi = r[0] * 10 ** fd
            ma = r[1] * 10 ** fd
            n = str(random.randint(mi, ma))
        nl = len(n)
        if fd + 1 - nl > 0:
            n = "0" * (fd + 1 - nl) + n  # Prepend with zeros if shorter that fraction digits
            nl += fd + 1 - nl
        return n[:nl - fd] + '.' + n[-fd:]
    elif dt == 'typedef':
        g = datatype_generators.get(r)
        if g:
            return g(datatype)
        else:
            return generate_random_data(typedefs[r], schema, module, node)  # Expand typedef
    elif dt in ['ns-leafref', 'leafref']:
        # TODO: leafref must point to an existing leaf
        path = r.split('/')
        # TODO: handle paths with paths inside [ ]
        # ex: "/oc-if:interfaces/oc-if:interface[oc-if:name=current()/../interface]/oc-if:subinterfaces/
        # oc-if:subinterface/oc-if:index"
        # TODO: Create function that tracks the datatype that the leafref points to.
        #       Needs to keep track of the current module when traversing back in the hierarchy
        if path[0] == '..':
            n = node
        else:
            n = schema
            path = path[1:]
        left_module_ns = False
        for m in path:
            if m == '..':
                if n.module is not None:
                    left_module_ns = True  # How to handle multiple exits and up/downs? Should probably not happen.
                n = n.parent
            else:
                if ':' in m:
                    prefix, m = m.split(':')
                    m = f'{schema.prefix2module(prefix)}:{m}'
                else:
                    if left_module_ns:
                        # How to handle when leaving multiple namespaces?
                        m = f'{module}:{m}'
                        left_module_ns = False
                try:
                    n = n.children[m]
                except KeyError as e:
                    print(f"ERROR: Failed to find leafref {r}", file=sys.stderr)
                    print(node.get_kp, module, file=sys.stderr)
                    print(n.get_kp, file=sys.stderr)
                    raise e
        kp = n.get_kp
        # TODO: Handle generator for a specific leaf
        if isinstance(n.parent, List) and n.name in n.parent.key_leafs:
            g = keypath_generators.get(kp[:-1])
            if g:
                return g(n.datatype)
        return generate_random_data(n.datatype, schema, module, n)
    elif dt == 'identityref':
        if r in identities:
            return pick_identity(identities, r)
        elif ':' in r:
            r_no_prefix = r.split(':')[1]
            if r_no_prefix in identities:
                return pick_identity(identities, r_no_prefix)

        raise Exception(f"Unknown identity: {r}")

    raise Exception(f"Unhandled datatype: {dt}")


def pick_identity(identities, r):
    return r if len(identities[r]) == 0 else random.choice(identities[r])


#############################################################################################################
#  Create config by iterating schema model
#############################################################################################################
@subcommand([
    argument('-f', '--format',
        choices=['default', 'tailf-config', 'nso-device'],
        default='default',
        help="config output format"
    ),
    argument('-n', '--name',
        type=str,
        default='ce0',
        help="Device name for output format nso-device"
    ),
    argument("-o", "--output",
         type=str,
         help="File to write generated config to."
     ),

    argument("-1", "--one-level",
         action="store_true",
         help="Show one level"
     )],
    help="show model tree"
)
def cmd_genconfig(args, schema):
    """
    Show the JSON schema tree.
    """
    doc, xmlroot = prepare_output(args)
    iter_schema(args, schema, xmlroot)

    output_file = open(args.output, 'w') if args.output else sys.stdout
    output_file.write(prettify(doc))
    exit(0)


class IterContext:
    def __init__(self):
        self.path = tuple()
        self.module = None


def create_list_entry(schema, doc, ch, tp, ctx):
    e = ET.SubElement(doc, ch.name)
    if ch.module:
        ctx.module = ch.module
        ns = get_ns(ch.module, schema.json)
        e.set('xmlns', ns)
    # TODO: Handle uniqueness of key
    g = keypath_generators.get(tp)
    if g:
        if not hasattr(g, '__iter__'):
            g = [g]
        for ln, klg in zip(ch.key_leafs, g):
            kl = ch.children[ln]
            ET.SubElement(e, ln).text = klg(kl.datatype)
    else:
        for ln in ch.key_leafs:
            kl = ch.children[ln]
            ET.SubElement(e, ln).text = generate_random_data(kl.datatype, schema, ctx.module, kl)
    return e


def add_levels(schema, doc, kp, ctx):
    ch = schema
    tp = tuple()
    for p in kp:
        tp += (p,)
        ch = ch.find(p)
        if isinstance(ch, Container):
            e = ET.SubElement(doc, ch.name)
            if ch.module:
                ctx.module = ch.module
                ns = get_ns(ch.module, schema.json)
                e.set('xmlns', ns)
            doc = e
        elif isinstance(ch, List):
            # Create a random number of list elements between 0 and 5
            n = 1  # random.randint(0, 2)
            if n > 0:
                for _ in range(0, n):
                    e = create_list_entry(schema, doc, ch, tp, ctx)
            doc = e
        else:
            print("ERROR: Type not supported with --path")
            sys.exit(1)
    return e


def iter_schema(args, schema, doc, ctx=None, ch=None):
    if ctx is None:
        ctx = IterContext()
        if args.path:
            kp = str2kp(args.path)
            ch = find_kp(schema, kp)
            if ch is None:
                print(f"Path {args.path} not found")
                sys.exit(1)
            doc = add_levels(schema, doc, kp, ctx)

    ch = ch or schema
    for k, t in ch:
        if ':' in k:
            m, k = k.split(':')
        tp = ctx.path + (k,)
        # Fix namespace support for verbose when path supports namespaces
        if args.verbose:
            print(f'Processing {kp2str(t.get_kp)}')
        if isinstance(t, Container):
            e = ET.SubElement(doc, k)
            if t.module:
                ctx.module = t.module
                ns = get_ns(t.module, schema.json)
                e.set('xmlns', ns)
            iter_schema(args, schema, e, ctx, t)
        elif isinstance(t, List):
            # Create a random number of list elements between 0 and 5
            n = 1  # random.randint(0, 2)
            if n > 0:
                for _ in range(0, n):
                    e = create_list_entry(schema, doc, t, tp, ctx)
                    iter_schema(args, schema, e, ctx, t)
        elif isinstance(t, Choice):
            m = t[random.choice(list(t.choices.keys()))]
            iter_schema(args, schema, doc, ctx, m.items())
        elif isinstance(t, Leaf):
            e = ET.SubElement(doc, k)
            g = keypath_generators.get(tp)
            if g:
                v = g(t.datatype)
            else:
                v = generate_random_data(t.datatype, schema, ctx.module, t)
            e.text = v
            if t.module:
                ns = get_ns(t.module, schema.json)
                e.set('xmlns', ns)
        else:
            raise Exception(f"Unhandled type {type(t)}")


def output_default():
    return '''\
<?xml version="1.0" ?>
<xml-root/>''', 'root', None


def output_nso_device(name):
    return f'''\
<?xml version="1.0" ?>
<config xmlns="http://tail-f.com/ns/config/1.0">
    <devices xmlns="http://tail-f.com/ns/ncs">
        <device>
            <name>{name}</name>
            <xml-root/>
        </device>
    </devices>
</config>''', 'config', 'http://tail-f.com/ns/ncs'


def output_config():
    return '''\
<?xml version="1.0" ?>
<xml-root/>''', 'config', "http://tail-f.com/ns/config/1.0"


def prepare_output(args):
    if args.format == 'default':
        fmt, rn, ns = output_default()
    elif args.format == 'nso-device':
        fmt, rn, ns = output_nso_device(args.name)
    elif args.format == 'tailf-config':
        fmt, rn, ns = output_config()

    doc = ET.fromstring(fmt)
    if doc.tag == 'xml-root':
        xmlroot = doc
    else:
        fns = f'{{{ns}}}' if ns else ''
        xmlroot = doc.find(f'.//{fns}xml-root')
    if rn is not None:
        xmlroot.tag = rn
    if ns is not None:
        xmlroot.attrib['xmlns'] = ns

    return doc, xmlroot


###########################################################################
#  Show model hierarchy tree
###########################################################################
@subcommand([
    argument("-l", "--leafs",
        action="store_true",
        help="Show leafs"
    ),
    argument("-1", "--one-level",
        action="store_true",
        help="Show one level"
    )],
    help="show model tree"
)
def cmd_tree(args, schema):
    """
    Show the JSON schema tree.
    """
    print_schema(args, schema)
    exit(0)


def print_schema(args, schema, indent=0):
    if indent == 0 and args.path:
        kp = str2kp(args.path)
        ch = find_kp(schema, kp)
        if ch is None:
            print(f"Path {args.path} not found")
            sys.exit(1)
        else:
            print_levels(schema, kp)
            indent = len(kp)
    else:
        ch = schema
    for k, t in ch:
        if args.verbose:
            print(f'Processing {kp2str(t.get_kp)}')
        if isinstance(t, Container):
            print(f"{' ' * (indent * 4)}{t.name} ", end='')
            if t.presence:
                print('(p-container)')
            else:
                print('(container)')
            if not args.one_level:
                print_schema(args, t, indent=indent + 1)
        elif isinstance(t, List):
            keys = ','.join(t.key_leafs)
            print(f"{' ' * (indent * 4)}{k} (list: {keys})")
            if not args.one_level:
                print_schema(args, t, indent=indent + 1)
        elif isinstance(t, Choice):
            # Only print container or list choices
            print(f"{' ' * (indent * 4)}{k} (choice)")
            for k2 in t.choices.keys():
                m = t[k2]
                print(f"{' ' * ((indent+1)*4)}{k2} (case) ({len(m)} member(s))")
                print_schema(args, m.items(), indent=indent + 2)
        elif isinstance(t, Leaf):
            if args.leafs:
                print(f"{' ' * (indent*4)}{k} (leaf) ({t.datatype[0]})")


def print_levels(schema, kp):
    indent = 0
    ch = schema
    for p in kp:
        ch = ch.find(p)
        if isinstance(ch, Container):
            print(f"{' ' * (indent * 4)}{ch.name} ", end='')
            if ch.presence:
                print('(p-container)')
            else:
                print('(container)')
        elif isinstance(ch, List):
            keys = ','.join(ch.key_leafs)
            print(f"{' ' * (indent * 4)}{ch.name} (list: {keys})")
        elif isinstance(ch, Choice):
            # Only print container or list choices
            print(f"{' ' * (indent * 4)}{ch.name} (choice)")
            for k in ch.choices.keys():
                m = ch[k]
                print(f"{' ' * ((indent+1) * 4)}{k} (case) ({len(m)} member(s))")
        indent += 1


#############################################################################################################
#  Print schema model complexity
#############################################################################################################
# TODO:
#  * Print note if leafref/when/must references outside --path.
@subcommand([
    argument("-1", "--one-level",
             action="store_true",
             help="Show one level"
             )],
    help="model complexity analysis"
)
def cmd_complex(args, schema):
    """
    Show the schema model complexity in terms of nested lists, choices, leaf concentrations,
    when/must expressions and leafrefs.
    """
    from rich.console import Console
    from rich.table import Table
    table = Table()
    table.add_column("List", justify="left", no_wrap=True)
    table.add_column("Keys", justify="left", no_wrap=True)
    table.add_column("No leafs", justify="right", no_wrap=True)
    ctx = print_schema_complexity(args, schema, table=table)
    console = Console()
    console.print(table)
    print()
    lf_table = Table()
    lf_table.add_column("Leafref", justify="left", no_wrap=True)
    lf_table.add_column("Path", justify="left", no_wrap=True)
    nslf_table = Table()
    nslf_table.add_column("Non-strict leafref", justify="left", no_wrap=True)
    nslf_table.add_column("Path", justify="left", no_wrap=True)
    for lf in ctx.leafrefs:
        dt, path = lf.datatype
        if dt == 'leafref':
            lf_table.add_row(kp2str(lf.get_kp), path)
        else:
            nslf_table.add_row(kp2str(lf.get_kp), path)
    console.print(nslf_table)
    print()
    console.print(lf_table)
    print()
    w_table = Table()
    w_table.add_column("When", justify="left", no_wrap=True)
    w_table.add_column("Xpath", justify="left", no_wrap=True)
    for w in ctx.whens:
        w_table.add_row(kp2str(w.get_kp), w.when)
    console.print(w_table)
    m_table = Table()
    m_table.add_column("Must", justify="left", no_wrap=True)
    m_table.add_column("Xpath", justify="left", no_wrap=True)
    for m in ctx.musts:
        m_table.add_row(kp2str(m.get_kp), m.must)
    print()
    console.print(m_table)
    exit(0)


def print_schema_complexity(args, schema, indent=0, table=None, ctx=None):
    root = ctx is None
    if indent == 0:
        if args.path:
            kp = str2kp(args.path)
            schema = find_kp(schema, kp)
            if schema is None:
                print(f"Path {args.path} not found")
                sys.exit(1)
            else:
                indent = len(kp)
                # TODO: Find equivalent for print_levels(schema, kp)
    if ctx is None:
        ctx = ComplexContext()
        cnt = count_leafs(args, schema, ctx)
        table.add_row(kp2str(schema.get_kp), '', f'{cnt}')
    for k, t in schema:
        if args.verbose:
            print(f'Processing {kp2str(t.get_kp)}')
        if t.when:
            ctx.whens.append(t)
        if t.must:
            ctx.musts.append(t)
        if isinstance(t, Container):
            if not args.one_level:
                print_schema_complexity(args, t, indent=indent, table=table, ctx=ctx)
        elif isinstance(t, List):
            cnt = count_leafs(args, t, ctx)
            keys = ','.join(t.key_leafs)
            kp = kp2str(t.get_kp2level(), starting_slash=False)
            table.add_row(f"{' ' * (indent * 4)}{kp}", f'{keys}', f'{cnt}')
            if not args.one_level:
                print_schema_complexity(args, t, indent=indent + 1, table=table, ctx=ctx)
        elif isinstance(t, Choice):
            # Only print container or list choices
            kp = kp2str(t.get_kp2level(), starting_slash=False)
            table.add_row(f"{' ' * (indent * 4)}{kp} (choice)", '', '')
            for k2 in t.choices.keys():
                m = t[k2]
                cnt = count_leafs(args, m.items(), ctx)
                table.add_row(f"{' ' * ((indent+1) * 4)}{k2} (case)", '', f'{cnt}')
                print_schema_complexity(args, m.items(), indent=indent + 2, table=table, ctx=ctx)
        elif isinstance(t, Leaf):
            dt, meta = t.datatype
            if dt in ['leafref', 'ns-leafref']:
                ctx.leafrefs.append(t)
    if root:
        return ctx


def count_leafs(args, ch, ctx):
    cnt = 0
    for k, t in ch:
        if isinstance(t, Container):
            cnt += count_leafs(args, t, ctx)
        elif isinstance(t, Leaf):
            cnt += 1
    return cnt


class ComplexContext:
    def __init__(self):
        self.leafrefs = []
        self.whens = []
        self.musts = []


#############################################################################################################
#  Generate a config generator descriptor
#############################################################################################################
# Approaches to generator a descriptor:
#  - Include every list and container
#  - Include only lists
#
# Options:
#  - Add default generators for key leafs (no specified --> use default generator)
#  - Add all leafs
#
# Options to add comments for:
#  - List keys
#  - Leafrefs
#  - Must statements
#  - When statements
#
# Questions:
#  - How to handle choices?
#   - Default is implicit?
#   - Explicit specification
#
# TODO:
#  * Add option for list/container and list strategies.
#  * Add option for including choice meta nodes (if possible to exclude)
#  * Add option for adding __NO_INSTANCES on lists and presence containers.
#  * Add option for including key leafs.
#  * Add option for including leafrefs.
#  * Add option for including when/must comments
#  *  - Comment if it references outside --path
@subcommand(
    help="generate config descriptor"
)
def cmd_gendesc(args, schema):
    """
    Generates a Python config generator descriptor and print on stdout.
    Currently, it includes:
     - Lists with key leafs as a comment.
     - Containers (presence containers are marked with a comment).
    """
    print_gen_desc(args, schema)


def print_gen_desc(args, schema, indent=0, root=True):
    if root:
        print('generator_descriptor = {')
    ch = schema
    if indent == 0:
        if args.path:
            kp = str2kp(args.path)
            ch = find_kp(ch, kp)
            if ch is None:
                print(f"Path {args.path} not found")
                sys.exit(1)
            else:
                print_desc_levels(schema, kp)
                indent = len(kp)
    n = 0
    pn = 0
    for k, t in ch:
        if pn != n:
            print(',')
        pn = n
        if args.verbose:
            print(f'Processing {kp2str(t.get_kp)}')
        if t.when:
            pass
        if t.must:
            pass
        if isinstance(t, Container):
            n += 1
            print(f"{' ' * ((indent+1) * 4)}\"{k}\": {{")
            print_gen_desc(args, t, indent=indent+1, root=False)
            print(f"{' ' * ((indent+1) * 4)}}}", end='')
        elif isinstance(t, List):
            n += 1
            keys = ','.join(t.key_leafs)
            print(f"{' ' * ((indent+1) * 4)}\"{k}\": {{  # {keys}")
            print_gen_desc(args, t, indent=indent+1, root=False)
            print(f"{' ' * ((indent+1) * 4)}}}", end='')
        elif isinstance(t, Choice):
            pass
            # Only print container or list choices
            # print(f"{' ' * (indent * 4)}{k} (choice)")
            # for k in t.choices.keys():
            #   m = t[k]
            #   cnt = count_leafs(args, m.items(), ctx)
            #   print(f"{' ' * ((indent+1) * 4)}{k} (case) ({len(m)} member(s)) leafs: {cnt}")
            #   print_schema_complexity(args, m.items(), indent=indent + 2)
        elif isinstance(t, Leaf):
            dt, meta = t.datatype
            if dt in ['leafref', 'ns-leafref']:
                pass
    print()
    if root:
        while indent>0:
            print(f"{' ' * (indent*4)}}}")
            indent -= 1
        print('}')


def print_desc_levels(schema, kp):
    indent = 0
    ch = schema
    for p in kp:
        ch = ch.find(p)
        if isinstance(ch, Container):
            print(f"{' ' * ((indent+1) * 4)}\"{ch.name}\": {{")
            if ch.presence:
                print('  # (p-container)')
        elif isinstance(ch, List):
            keys = ','.join(ch.key_leafs)
            print(f"{' ' * ((indent+1) * 4)}\"{ch.name}\": {{  # {keys}")
        elif isinstance(ch, Choice):
            # TODO: Handle choice
            pass
#            print(f"{' ' * (indent * 4)}{ch.name} (choice)")
#            for k in ch.choices.keys():
#                m = ch[k]
#                print(f"{' ' * ((indent+1) * 4)}{k} (case) ({len(m)} member(s))")                print(f"{' ' * ((indent+1) * 4)}{k} (case) ({len(m)} member(s))")
        indent += 1


#############################################################################################################
#  Run config generator descriptor
#############################################################################################################
# TODO:
#  * Output to xml.
#  * Use generate_random_data to set leaf values.
#  * Handle choices.
#  * Handle list key uniqueness.
#  * Override datatype generators (list/dict/...?)
#  * Add support for Python generator functions. Useful for sequences.
#  * Add support for variables (same as/close to Python generator functions?)
#
# IDEAS:
#  * __SKIP: List of paths to skip.
#  * __SKIP_THIS: True/False
#  * Option for strategies for unspecified leafs
#  * Option how to iterate container and leafs: separate/togehter
#  * Option which unspecified leafs to set: all/percent/random
#  * How to handle invalid entries: stop-on-error, warning-on-error?
#  * Ideas for strategies for how to iterate
#    - Visit only nodes in descriptor.
#    - Visit all nodes specified by --path, alter with descriptor.
#    - ...
@subcommand([
    argument("descriptor",
             type=str,
             help="The descriptor file to run"
    )],
    help="run config descriptor"
)
def cmd_rundesc(args, schema):
    """
    Runs a config generator descriptor.
    Currently, it has the features:
     - Visits all specified lists and containers.
     - Calls generator functions for list key leafs.
     - List entry create can be controlled with __NO_INSTANCES.
    """
    # TODO: Check descriptor file existence and print appropriate error message when not found or execution failure.
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(args.descriptor, args.descriptor)
    spec = importlib.util.spec_from_loader(args.descriptor, loader)
    mymodule = importlib.util.module_from_spec(spec)
    loader.exec_module(mymodule)
    iterate_descriptor(args, schema, mymodule.generator_descriptor)


def iterate_descriptor(args, schema, desc):
    __no_instances = 1 # Used by lists
    # Process any processing directives starting with double underscore.
    for k, v in desc.items():
        if k.startswith('__'):
            if k == '__NO_INSTANCES':
                if isinstance(schema, List):
                    __no_instances = v
                else:
                    print("ERROR: __NO_INSTAMCES only valid for list nodes:", schema.name, str(type(schema)))
                    sys.exit(1)
    if isinstance(schema, List):
        if callable(__no_instances):
            noi = __no_instances(schema)
        else:
            noi = __no_instances
        for _ in range(0, noi):
            print("Creating list entry:", schema.name)
            processed = []  # List of processed nodes
            for leaf in schema.key_leafs:
                processed.append(leaf)
                n = schema.find_path(leaf)
                if leaf not in desc.keys():
                    process_leaf_default(args, n)
                else:
                    process_leaf(args, n, desc[leaf])
            process_members(args, schema, desc, processed)
    elif isinstance(schema, Container):
        # TODO: How should containers be processed: part of the leafs or separately
        print("Processing container", schema.name)
        if schema.presence:
            pass  # Handle presence container
        process_members(args, schema, desc, [])
    elif isinstance(schema, Schema):
        process_members(args, schema, desc, [])
    else:
        print("ERROR: Invalid node", str(type(schema)), desc)
        sys.exit(1)


def process_members(args, schema, desc, processed):
    for k, v in desc.items():
        if k.startswith('__'):
            pass  # Processing directives alread handled
        elif k not in processed:
            # TODO: Handle mandatory leafs
            processed.append(k)
            n = schema.find_path(k)
            if isinstance(v, dict):
                iterate_descriptor(args, n, v)
            else:
                process_leaf(args, n, v)


def process_leaf(_args, schema, desc):
    assert (isinstance(schema, Leaf))
    if callable(desc):  # Only valid for leafs
        value = desc(schema)
    else:
        value = desc
    print(f"{schema.name} set to {value}")


def process_leaf_default(_args, schema):
    assert (isinstance(schema, Leaf))
    print("Setting leaf", schema.name, 'to default generated value')


#############################################################################################################
#  Main
#############################################################################################################
def main():
    global parser, subparsers
    set_epilog(parser, subparsers)
    args = parser.parse_args(sys.argv[1:])

    if args.subcommand is None:
        parser.print_help()
    else:
        # TODO: Check file existence and print appropriate error message when not found.
        json_schema = json.loads(open(args.model).read())
        schema = Schema(json_schema)
        args.func(args, schema)
    sys.exit()

if __name__ == "__main__":
    main()
