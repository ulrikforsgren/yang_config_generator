#!/usr/bin/env python3

import sre_parse
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


def set_epilog():
    global parser, subparsers
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


def subcommand(arguments=None, help='', parent=subparsers):
    arguments = arguments or []
    if not hasattr(parent, 'cmds'): parent.cmds = []

    def decorator(func):
        name = func.__name__[4:]
        p = parent.add_parser(name, description=func.__doc__)
        for t, args, kwargs in arguments:
            if t == 'a':
                p.add_argument(*args, **kwargs)
            elif t == 'm':
                g = p.add_mutually_exclusive_group(**kwargs)
                for _, a, kw in args:
                    g.add_argument(*a, **kw)
        p.set_defaults(func=func)

        def strip_prefix(s):
            return s[len(p.prog) + 8:].rstrip()

        parent.cmds.append((name, strip_prefix(p.format_usage()),
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

    def find(self, p, find_in_choice=True):
        module, name = p
        for ch in self.children.values():
            if find_in_choice and isinstance(ch, Choice):
                ch = ch.find(p)
                if ch is not None:
                    return ch
            elif name == ch.name and (module is None or module == ch.module):
                return ch
        return None

    def find_path(self, p, find_in_choice=True):
        m = None
        n = p
        if ':' in p:
            m, n = p.split(':')
        return self.find((m, n), find_in_choice)


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

    def find(self, p, find_in_choice=True):
        module, name = p
        for case in self.choices.values():
            for _, ch in case.items():
                if isinstance(ch, Choice):
                    ch = ch.find(p, find_in_choice)
                    if ch is not None:
                        return ch
                elif name == ch.name and (module is None or module == ch.module):
                    return ch
        return None

    def find_path(self, p, find_in_choice=True):
        m = None
        n = p
        if ':' in p:
            m, n = p.split(':')
        return self.find((m, n), find_in_choice)


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
            pattern = patterns[0]
        else:
            pattern = "[a-zA-Z0-9 ._]+"
        if lengths:
            length = random.choice(lengths)  # Select a random length
            lmin, lmax = length
            lmax = lmax or lmin
        else:
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
        path = r.split('/')
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
#  Output backends
#############################################################################################################
class OutputBackend:
    def __init__(self, schema):
        self.schema = schema

    def add_container(self, name, module):
        return "container node"
    def add_list_entry(self, name, module, keys, values):
        return "list entry"

    def add_leaf(self, name, module, value):
        pass

class XMLBackend(OutputBackend):
    def __init__(self, schema, doc):
        super().__init__(schema)
        self.doc = doc

    def add_container(self, name, module):
        e = ET.SubElement(self.doc, name)
        if module:
            ns = get_ns(module, self.schema.json)
            e.set('xmlns', ns)
        return XMLBackend(self.schema, e)

    def add_list_entry(self, name, module, key_leafs, values):
        e = ET.SubElement(self.doc, name)
        if module:
            ns = get_ns(module, self.schema.json)
            e.set('xmlns', ns)
        doc = XMLBackend(self.schema, e)
        for key, value in zip(key_leafs, values):
            doc.add_leaf(key, module, value)
        return doc

    def add_leaf(self, name, module, value):
        e = ET.SubElement(self.doc, name)
        e.text = value
        if module:
            ns = get_ns(module, self.schema.json)
            e.set('xmlns', ns)


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
    outputroot = XMLBackend(schema, xmlroot)
    iter_schema(args, schema, outputroot)

    output_file = open(args.output, 'w') if args.output else sys.stdout
    output_file.write(prettify(doc))
    exit(0)


class IterContext:
    def __init__(self):
        self.path = tuple()
        self.module = None


def create_list_entry(schema, doc, ch, tp, ctx):
    if ch.module:
        ctx.module = ch.module
    g = keypath_generators.get(tp)
    values = []
    if g:
        if not hasattr(g, '__iter__'):
            g = [g]
        for ln, klg in zip(ch.key_leafs, g):
            kl = ch.children[ln]
            values.append(klg(kl.datatype))
    else:
        for ln in ch.key_leafs:
            kl = ch.children[ln]
            values.append(generate_random_data(kl.datatype, schema, ctx.module, kl))
    return doc.add_list_entry(ch.name, ch.module, ch.key_leafs, values)



def add_levels(schema, doc, kp, ctx):
    ch = schema
    tp = tuple()
    for p in kp:
        tp += (p,)
        ch = ch.find(p)
        if isinstance(ch, Container):
            e = doc.add_container(ch.name, ch.module)
            if ch.module:
                ctx.module = ch.module
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
            e = doc.add_container(k, t.module)
            if t.module:
                ctx.module = t.module
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
            g = keypath_generators.get(tp)
            if g:
                v = g(t.datatype)
            else:
                v = generate_random_data(t.datatype, schema, ctx.module, t)
            doc.add_leaf(k, t.module, v)
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
    if args.format == 'nso-device':
        fmt, rn, ns = output_nso_device(args.name)
    elif args.format == 'tailf-config':
        fmt, rn, ns = output_config()
    else:  # default
        fmt, rn, ns = output_default()

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
@subcommand([
    argument("-1", "--one-level",
             action="store_true",
             help="Show one level"
             ),
    argument("--rich",
             action="store_true",
             help="Show data using rich tables"
             ),
    argument("--hide-choice",
             action="store_true",
             help="Hide choices in lists view"
             ),
    argument("-l", "--lists",
             action="store_true",
             help="Show lists"
             ),
    argument("-n", "--ns-leafrefs",
             action="store_true",
             help="Show non-strict leafrefs"
             ),
    argument("-r", "--leafrefs",
             action="store_true",
             help="Show leafrefs"
             ),
    argument("-w", "--whens",
             action="store_true",
             help="Show when statements"
             ),
    argument("-m", "--musts",
             action="store_true",
             help="Show must statements"
             ),
    argument("-p", "--patterns",
             action="store_true",
             help="Show patterns"
             )],
    help="model complexity analysis"
)
def cmd_complex(args, schema):
    """
    Show the schema model complexity in terms of nested lists, choices, leaf concentrations,
    when/must expressions and leafrefs.
    """
    if not (args.lists or args.ns_leafrefs or args.leafrefs or args.whens or args.musts or args.patterns):
        args.lists = args.ns_leafrefs = args.leafrefs = args.whens = args.musts = args.patterns = True
    if args.rich:
        from rich.console import Console
        from rich.table import Table
        console = Console()
    ctx = collect_schema_complexity(args, schema, schema)
    if args.lists:
        print()
        if args.rich:
            table = Table()
            table.add_column("List", justify="left", no_wrap=True)
            table.add_column("Keys", justify="left", no_wrap=True)
            table.add_column("No leafs", justify="right", no_wrap=True)
            for indent, kp, keys, count in ctx.lists:
                table.add_row(f"{' ' * (indent * 4)}{kp}", f'{keys}', f'{count}')
            console.print(table)
        else:
            for indent, kp, keys, count in ctx.lists:
                strkp = f"{' ' * (indent * 4)}{kp}"
                print(f"{strkp:<120}", f'{keys:<20}', f'{count:>5}')
    if args.ns_leafrefs:
        print()
        if args.rich:
            nslf_table = Table()
            nslf_table.add_column("Non-strict leafref", justify="left", no_wrap=True)
            nslf_table.add_column("Path", justify="left", no_wrap=True)
            for lf in ctx.ns_leafrefs:
                nslf_table.add_row(kp2str(lf.get_kp), lf.datatype[1])
            console.print(nslf_table)
        else:
            for lf in ctx.ns_leafrefs:
                print(f'{kp2str(lf.get_kp):<120} {lf.datatype[1]}')

    if args.leafrefs:
        print()
        if args.rich:
            lf_table = Table()
            lf_table.add_column("Leafref", justify="left", no_wrap=True)
            lf_table.add_column("Path", justify="left", no_wrap=True)
            for lf in ctx.leafrefs:
                lf_table.add_row(kp2str(lf.get_kp), lf.datatype[1])
            console.print(lf_table)
        else:
            for lf in ctx.leafrefs:
                print(f'{kp2str(lf.get_kp):<120} {lf.datatype[1]}')
    if args.whens:
        print()
        if args.rich:
            w_table = Table()
            w_table.add_column("When", justify="left", no_wrap=True)
            w_table.add_column("Xpath", justify="left", no_wrap=True)
            for w in ctx.whens:
                w_table.add_row(kp2str(w.get_kp), w.when)
            console.print(w_table)
        else:
            for w in ctx.whens:
                print(f"{kp2str(w.get_kp):<120} {w.when}")
    if args.musts:
        print()
        if args.rich:
            m_table = Table()
            m_table.add_column("Must", justify="left", no_wrap=True)
            m_table.add_column("Xpath", justify="left", no_wrap=True)
            for m in ctx.musts:
                m_table.add_row(kp2str(m.get_kp), m.must)
            console.print(m_table)
        else:
            for w in ctx.whens:
                print(f"{kp2str(w.get_kp):<120} {w.when}")
    if args.patterns:
        print()
        if args.rich:
            p_table = Table()
            p_table.add_column("Pattern", justify="left", no_wrap=False)
            p_table.add_column("Count", justify="right", no_wrap=True)
            p_table.add_column("Min", justify="right", no_wrap=True)
            p_table.add_column("Max", justify="right", no_wrap=True)
            for pattern, count in ctx.patterns.items():
                strpattern = f'"{pattern}"'
                if pattern:
                    mi, ma = rstr.xeger_minmax(pattern)
                else:
                    pattern = "(string)"
                    mi = 0
                    ma = sre_parse.MAXREPEAT
                p_table.add_row(pattern, str(count), str(mi), str(ma))
            console.print(p_table)
        else:
            for pattern, count in ctx.patterns.items():
                strpattern = f'"{pattern}"'
                if pattern:
                    mi, ma = rstr.xeger_minmax(pattern)
                else:
                    pattern = "(string)"
                    mi = 0
                    ma = sre_parse.MAXREPEAT
                print(f"{strpattern:<120} {count:>6} {mi:>4} - {ma:>6}")
    exit(0)


def collect_schema_complexity(args, schema, node, indent=0, ctx=None):
    root = ctx is None
    if indent == 0:
        if args.path:
            kp = str2kp(args.path)
            node = find_kp(node, kp)
            if node is None:
                print(f"Path {args.path} not found")
                sys.exit(1)
            else:
                indent = len(kp)
    if ctx is None:
        ctx = ComplexContext()
        cnt = count_leafs(args, node, ctx)
        ctx.lists.append((0, kp2str(node.get_kp), '', cnt))
    for k, t in node:
        if args.verbose:
            print(f'Processing {kp2str(t.get_kp)}')
        if t.when:
            ctx.whens.append(t)
        if t.must:
            ctx.musts.append(t)
        if isinstance(t, Container):
            if not args.one_level:
                collect_schema_complexity(args, schema, t, indent=indent, ctx=ctx)
        elif isinstance(t, List):
            cnt = count_leafs(args, t, ctx)
            keys = ','.join(t.key_leafs)
            kp = kp2str(t.get_kp2level(), starting_slash=False)
            ctx.lists.append((indent, kp, keys, cnt))
            if not args.one_level:
                collect_schema_complexity(args, schema, t, indent=indent + 1, ctx=ctx)
        elif isinstance(t, Choice):
            # Only print container or list choices
            kp = kp2str(t.get_kp2level(), starting_slash=False)
            if not args.hide_choice:
                ctx.lists.append((indent, f'{kp} (choice)', '', ''))
            for k2 in t.choices.keys():
                m = t[k2]
                cnt = count_leafs(args, m.items(), ctx)
                if not args.hide_choice:
                    ctx.lists.append((indent+1, f'{k2} (case)', '', cnt))
                collect_schema_complexity(args, schema, m.items(), indent=indent + 2, ctx=ctx)
        elif isinstance(t, Leaf):
            dt, meta = t.datatype
            if dt == 'leafref':
                ctx.leafrefs.append(t)
            elif dt == 'ns-leafref':
                ctx.ns_leafrefs.append(t)
            collect_patterns(schema, ctx, t.datatype)
    if root:
        return ctx


def collect_patterns(schema, ctx, datatype):
    def inc_pattern(pattern):
        if not pattern in ctx.patterns:
            ctx.patterns[pattern] = 1
        else:
            ctx.patterns[pattern] += 1
    typedefs = schema.json['typedefs']
    dt, r = datatype
    if dt == 'string':
        _lengths, patterns = r
        if patterns:
            for pattern in patterns:
                inc_pattern(pattern)
        else:
            inc_pattern("")
    elif dt == 'typedef':
        collect_patterns(schema, ctx, typedefs[r])
    elif dt == 'union':
        for case in r:
            collect_patterns(schema, ctx, case)


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
        self.lists =[]
        self.ns_leafrefs = []
        self.leafrefs = []
        self.whens = []
        self.musts = []
        self.patterns = {}


#############################################################################################################
#  Generate a config generator descriptor
#############################################################################################################
# Approaches to generate a descriptor:
#  - Include every list, container and choice
#  - No specification of number of list elements.
#  - No leafs are specified.
#
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
        if args.verbose:
            print(f'Processing {kp2str(t.get_kp)}')
        if t.when:
            pass
        if t.must:
            pass
        if isinstance(t, Container):
            if pn != n:
                print(',')
                pn = n
            n += 1
            print(f"{' ' * ((indent+1) * 4)}\"{k}\": {{", end='')
            if not t.presence:
                print()
            else:
                print("  # (p-container)")
            print_gen_desc(args, t, indent=indent+1, root=False)
            print(f"{' ' * ((indent+1) * 4)}}}", end='')
        elif isinstance(t, List):
            if pn != n:
                print(',')
                pn = n
            n += 1
            keys = ','.join(t.key_leafs)
            print(f"{' ' * ((indent+1) * 4)}\"{k}\": {{  # {keys}")
            print_gen_desc(args, t, indent=indent+1, root=False)
            print(f"{' ' * ((indent+1) * 4)}}}", end='')
        elif isinstance(t, Choice):
            if pn != n:
                print(',')
                pn = n
            n += 1
            print(f"{' ' * ((indent+1) * 4)}\"{k}\": {{  # (choice)")
            n2 = 0
            pn2 = 0
            for k in t.choices.keys():
                if pn2 != n2:
                    print(',')
                    pn2 = n2
                n2 += 1
                m = t[k]
                print(f"{' ' * ((indent+2) * 4)}\"{k}\": {{  # (case)")
                print_gen_desc(args, m.items(), indent=indent + 2, root=False)
                print(f"{' ' * ((indent+2) * 4)}}}", end='')
            if n2:
                print()
            print(f"{' ' * ((indent + 1) * 4)}}}", end='')
        elif isinstance(t, Leaf):
            dt, meta = t.datatype
            if dt in ['leafref', 'ns-leafref']:
                pass
    if n:
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
#  * Handle choices.
#  * Handle list key uniqueness.
#  * Override datatype generators (list/dict/...?)
#  * Add support for Python generator functions. Useful for sequences.
#    - Control when they are initiated/resetted
#  * Add support for variables (same as/close to Python generator functions?)
#
# IDEAS:
#  * __SKIP_THIS: True/False
#  * Support function/generators for __SKIP control directive.
#  * Option for strategies for unspecified leafs
#  * Option how to iterate container and leafs: separate/togehter
#  * Option which unspecified leafs to set: all/percent/random
#  * How to handle invalid entries: stop-on-error, warning-on-error?
#  * Ideas for strategies for how to iterate
#    - Visit only nodes in descriptor.
#    - Visit all nodes specified by --path, alter with descriptor.
#    - Specify leafs witout or with containers: "name", "ntp/server/name"? Focus on lists.
#    - ...
@subcommand([
    argument("descriptor",
             type=str,
             help="The descriptor file to run"
    ),
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
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(args.descriptor, args.descriptor)
    spec = importlib.util.spec_from_loader(args.descriptor, loader)
    mymodule = importlib.util.module_from_spec(spec)
    loader.exec_module(mymodule)

    doc, xmlroot = prepare_output(args)
    output = XMLBackend(schema, xmlroot)
    iterate_descriptor(args, schema, schema, output, mymodule.generator_descriptor)

    output_file = open(args.output, 'w') if args.output else sys.stdout
    output_file.write(prettify(doc))


def iterate_descriptor(args, schema, s_node, doc, desc):
    __no_instances = 1 # Used by lists, default is one instance
    __choose = None # Used by choices, default is random
    # Process any processing directives starting with double underscore.
    for k, v in desc.items():
        if k.startswith('__'):
            if k == '__NO_INSTANCES':
                if isinstance(s_node, List):
                    __no_instances = v
                else:
                    print("ERROR: __NO_INSTAMCES only valid for list nodes:", s_node.name, str(type(s_node)))
                    sys.exit(1)
            elif k == '__CHOOSE':
                if isinstance(s_node, Choice):
                    __choose = v
                else:
                    print("ERROR: __NO_INSTAMCES only valid for list nodes:", s_node.name, str(type(s_node)))
                    sys.exit(1)
            elif k == '__SKIP' and v == True:
                return
    if isinstance(s_node, Schema):
        process_members(args, schema, s_node, doc, desc, [])
    elif isinstance(s_node, List):
        noi = eval_leaf_value(s_node, __no_instances)
        for _ in range(0, noi):
            processed = []  # List of processed nodes
            values = []
            for leaf in s_node.key_leafs:
                processed.append(leaf)
                n = s_node.find_path(leaf)
                if leaf not in desc.keys():
                    values.append(process_leaf_default(args, schema, n))
                else:
                    values.append(eval_leaf_value(n, desc[leaf]))
            le = doc.add_list_entry(s_node.name, s_node.module, s_node.key_leafs, values)
            process_members(args, schema, s_node, le, desc, processed)
            create_unspecified_leafs(args, schema, s_node, le, desc, processed)
    elif isinstance(s_node, Container):
        processed = []
        e = doc.add_container(s_node.name, s_node.module)
        if s_node.presence:
            pass  # Handle presence container

        process_members(args, schema, s_node, e, desc, processed)
        create_unspecified_leafs(args, schema, s_node, e, desc, processed)
    elif isinstance(s_node, Choice):
        if __choose is None:
            case = random.choice(list(s_node.choices))
        else:
            case = eval_leaf_value(__choice)
        case_nodes = s_node.choices[case]
        processed = []
        process_members(args, schema, s_node, doc, desc[case], processed)
        create_unspecified_leafs(args, schema, Case(s_node[case]), doc, desc[case], processed)

    else:
        print("ERROR: Invalid node", str(type(s_node)), desc)
        sys.exit(1)


# TODO: Incorporate or move this to Schema?
class Case(HasChildren):
    def __init__(self, case_children):
        self.children = case_children


def eval_leaf_value(s_node, value):
    if callable(value):
        return value(s_node)
    elif hasattr(value, '__next__'):
        return value.__next__()
    elif isinstance(value, tuple):
        func, *args = value
        assert(callable(func))
        return func(*args)
    else:
        return value
def create_unspecified_leafs(args, schema, s_node, doc, desc, processed):
    for k, v in s_node.children.items():
        if isinstance(v, Leaf) and k not in desc.keys() and k not in processed:
            doc.add_leaf(k, None, process_leaf_default(args, schema, v))



def process_members(args, schema, s_node, doc, desc, processed):
    for k, v in desc.items():
        if k.startswith('__'):
            pass  # Processing directives already handled
        elif k not in processed:
            # TODO: Improve test with processed
            processed.append(k)
            n = s_node.find_path(k, find_in_choice=False)
            if isinstance(v, dict):
                iterate_descriptor(args, schema, n, doc, v)
            else:
                doc.add_leaf(k, None, eval_leaf_value(n, v))


def process_leaf_default(_args, schema, s_node):
    assert (isinstance(s_node, Leaf))
    return generate_random_data(s_node.datatype, schema, s_node.module, s_node)


#############################################################################################################
#  Main
#############################################################################################################
def main():
    global parser, subparsers
    set_epilog()
    args = parser.parse_args(sys.argv[1:])

    if args.subcommand is None:
        parser.print_help()
    else:
        json_schema = json.loads(open(args.model).read())
        schema = Schema(json_schema)
        args.func(args, schema)
    sys.exit()

if __name__ == "__main__":
    main()
