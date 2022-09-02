#!/usr/bin/env python3

import argparse
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
#  - How shold leafrefs be handled?
#    Get a value if exists/create if not?
#    Create anyway if non-strict ...
#  - Handle uniqueness of list keys
#  - Refactor generate_random_data to take only node as input.
#  - Should there be a default generator for each native type?
#    To gets rid of the if mess...
#    Easier to override types?!
#  - Regexp like matching to create generator for arbitrary part of the model?
#  - Handle min-elements/max-elements.


def parseArgs(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--module', type=str, required=True,
                        help='Compiled YANG module (json)')
    parser.add_argument('-o', '--output', type=str, required=False,
                        help='Output file name')
    parser.add_argument('--hierarchy', required=False, action='store_true', default=False)
    parser.add_argument('--one-level', required=False, action='store_true', default=False)
    parser.add_argument('-v', dest='verbose', required=False,
                        action='store_true', default=False)
    parser.add_argument('-f', '--format', choices=['default', 'tailf-config', 'nso-device'], default='default')
    parser.add_argument('-n', '--name', required=False, type=str, default='ce0')
    return parser.parse_args(args)


class Node:
    def __init__(self, parent, name, module=None):
        self.parent = parent
        self.name = name
        self.module = module

    def get_kp(self):
        kp = []
        node = self
        while isinstance(node, Node):
            kp = [(node.module, node.name)] + kp
            node = node.parent
        return tuple(kp)


def kp2str(path):
    s = ""
    if len(path) == 0:
        return '/'
    for m, n in path:
        if m is not None:
            s += f'/{m}:{n}'
        else:
            s += f'/{n}'
    return s


class Container(Node):
    def __init__(self, parent, name, module=None):
        super().__init__(parent, name, module)
        self.children = {}

    def __iter__(self):
        for k, v in self.children.items():
            yield k, v


class Choice(Node):
    def __init__(self, parent, name):
        super().__init__(parent, name)
        self.choices = {}

    def __iter__(self):
        for k, v in self.choices.items():
            yield k, v

    def __len__(self):
        return len(self.choices)

    def __getitem__(self, n):
        return self.choices[n]


class List(Node):
    def __init__(self, parent, name, key_leafs, module=None):
        super().__init__(parent, name, module)
        self.key_leafs = [l[1] for l in key_leafs]
        self.children = {}  # All children
        self.nk_children = {}  # Non key children

    def __iter__(self):
        for k, v in self.nk_children.items():
            yield k, v


class Leaf(Node):
    def __init__(self, parent, name, datatype, module=None):
        super().__init__(parent, name, module)
        self.datatype = datatype
        self.children = {}


class LeafList(Leaf):
    pass


class Schema:
    def __init__(self, schema=None):
        self.json = schema
        self.children = {}
        if schema is not None:
            load_schema(schema['tree'], self)

    def get_kp(self):
        return []

    def prefix2module(self, prefix):
        for m_name, (m_prefix, m_ns) in self.json['modules'].items():
            if prefix == m_prefix:
                return m_name
        return None

    def __iter__(self):
        for k, v in self.children.items():
            yield k, v


def load_schema(schema, node, children=None, parent=None):
    children = children if children is not None else node.children
    parent = parent or node
    for k, v in schema.items():
        nn = None
        m = None
        mk = k
        if ':' in k:
            m, k = k.split(':')
        # print(k)
        t, dt, *r = v
        if t == 'container':
            nn = Container(parent, k, m)
            load_schema(dt, nn)
        elif t == 'list':
            nn = List(parent, k, r[0], m)
            load_schema(dt, nn)
            for c, v in nn.children.items():
                if c not in nn.key_leafs:
                    nn.nk_children[c] = v
        elif t == 'choice':
            nn = Choice(parent, k)
            for case, v in dt.items():
                c = {}
                nn.choices[case] = c
                load_schema(v, nn, parent=parent, children=c)
            pass
        elif t == 'leaf':
            nn = Leaf(parent, k, dt, m)
        elif t == 'leaf-list':
            nn = LeafList(parent, k, dt, m)
        else:
            raise Exception(f'Unhandled type {t}')
        if nn is not None:
            children[mk] = nn


def compile_keypath_generators(d):
    g = {}
    for k, v in d.items():
        assert (k[0] == '/')
        kp = k.split('/')[1:]
        g[tuple(kp)] = v
    return g


def string_generator(datatype):
    return rstr.xeger("[a-z][a-z0-9_-]+")


def ulrik_generator(datatype):
    return rstr.xeger("[uU][lL][rR][iI][kK]")


def ipv4_generator(datatype):
    return '{}.{}.{}.{}'.format(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255),
                                random.randint(0, 255))


def ipv4_prefix_generator(datatype):
    return '{}.{}.{}.{}/{}'.format(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255),
                                   random.randint(0, 255), random.randint(1, 32))


def ipv6_generator(datatype):
    return '{:04X}:{:04X}::{:02X}'.format(random.randint(0, 65535), random.randint(0, 65535), random.randint(0, 255))


def ipv6_prefix_generator(datatype):
    return '{:04X}:{:04X}::{:02X}/{}'.format(random.randint(0, 65535), random.randint(0, 65535), random.randint(0, 255),
                                             random.randint(0, 127))


def rd_generator(datatype):
    return '{}:{}'.format(random.randint(0, 65535), random.randint(0, 255))


def uint16_generator(datatype):
    return str(random.randint(0, 511))


def uint16sub_generator(datatype):
    return '{}.{}'.format(random.randint(0, 511), random.randint(0, 128))


def eth_generator(datatype):
    return '{}/{}'.format(random.randint(0, 66), random.randint(0, 128))


def permit_expr_generator(datatype):
    """
  ((internet)|(local-AS)|(no-advertise)|(no-export)|(\\d+:\\d+)|(\\d+))( (internet)|(local-AS)|(no-advertise)|(no-export)|(\\d+:\\d+)|(\\d+))*
    """
    # TODO: Create function from the regexp above...
    return 'internet'


def permit_generator(datatype):
    return rstr.xeger("(permit|deny|remark) [a-z ]{5-15}")


def acl_generator(datatype):
    return rstr.xeger(
        "(permit [a-z ]{5,15})|(deny [a-z ]{5,15})|(remark [a-z ]{5,15})|([0-9]+)|(dynamic [a-z ]{5,15})|(evaluate [a-z ]{5,15})")


def acl2_generator(datatype):
    return rstr.xeger("(permit [a-z ]{5,15})|(deny [a-z ]{5,15})|(remark [a-z ]{5,15})|([0-9]+)|(dynamic [a-z ]{5,15})")


def hex_generator(datatype):
    return rstr.xeger("[a-fA-F0-9]*")


def aaa_name_generator(datatype):
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
    "((internet)|(local-AS)|(no-advertise)|(no-export)|(\\d+:\\d+)|(\\d+))( (internet)|(local-AS)|(no-advertise)|(no-export)|(\\d+:\\d+)|(\\d+))*": permit_expr_generator,
    "((internet)|(local\\-AS)|(no\\-advertise)|(no\\-export)|(\\d+:\\d+)|(\\d+))( (internet)|(local\\-AS)|(no\\-advertise)|(no\\-export)|(\\d+:\\d+)|(\\d+))*": permit_expr_generator,
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
    v = None
    if dt == 'union':
        # Select one random datatype in the union
        dt, r = random.choice(r)

    g = datatype_generators.get(dt)
    if g: return g(datatype)
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
                X
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
            if mx is None: mx = mi
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
        l = len(n)
        if fd + 1 - l > 0:
            n = "0" * (fd + 1 - l) + n  # Prepend with zeros if shorter that fraction digits
            l += fd + 1 - l
        return n[:l - fd] + '.' + n[-fd:]
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
        # ex: "/oc-if:interfaces/oc-if:interface[oc-if:name=current()/../interface]/oc-if:subinterfaces/oc-if:subinterface/oc-if:index"
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
                if n.module is not None: left_module_ns = True  # How to handle multiple exits and up/downs?
                                                                # Should probably not happen.
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
                    print(node.get_kp(), module, file=sys.stderr)
                    print(n.get_kp(), file=sys.stderr)
                    raise e
        kp = n.get_kp()
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


def get_ns(m, schema):
    return schema['modules'][m][1]


class IterContext:
    def __init__(self):
        self.path = tuple()
        self.module = None


def iter_schema(args, schema, doc, ctx=None, ch=None):
    # TODO: Keep track of current module
    #       Move path into context object and pass that to iter_schema
    ctx = ctx or IterContext()
    ch = ch or schema
    for k, t in ch:
        if ':' in k:
            m, k = k.split(':')
        tp = ctx.path + (k,)
        # Fix namespace support for verbose when path supports namespaces
        if args.verbose: print(f'Processing {kp2str(t.get_kp())}')
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
                    e = ET.SubElement(doc, k)
                    if t.module:
                        ctx.module = t.module
                        ns = get_ns(t.module, schema.json)
                        e.set('xmlns', ns)
                    # TODO: Handle uniqueness of key
                    g = keypath_generators.get(tp)
                    if g:
                        if not hasattr(g, '__iter__'):
                            g = [g]
                        for ln, klg in zip(t.key_leafs, g):
                            kl = t.children[ln]
                            ET.SubElement(e, ln).text = klg(kl.datatype)
                    else:
                        for ln in t.key_leafs:
                            kl = t.children[ln]
                            ET.SubElement(e, ln).text = generate_random_data(kl.datatype, schema, ctx.module, kl)
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


def print_schema(args, ch, indent=0):
    for k, t in ch:
        if args.verbose:
            print(f'Processing {kp2str(t.get_kp())}')
        if isinstance(t, Container):
            print(f"{' ' * (indent * 4)}{k} (container)")
            if not args.one_level:
                print_schema(args, t, indent=indent + 1)
        elif isinstance(t, List):
            keys = ','.join(t.key_leafs)
            print(f"{' ' * (indent * 4)}{k} (list: {keys})")
            if not args.one_level:
                print_schema(args, t, indent=indent + 1)
        elif isinstance(t, Choice):
            # Only print container or list choices
            for k in t.choices.keys():
                print(f"{' ' * (indent * 4)}{k} (choice")
                m = t[k]
                print_schema(args, m.items(), indent=indent + 1)


def output_default():
    return '''<?xml version="1.0" ?>
        <xml-root/>''', 'root', None


def output_nso_device(name):
    return f'''<?xml version="1.0" ?>
<config xmlns="http://tail-f.com/ns/config/1.0">
<devices xmlns="http://tail-f.com/ns/ncs">
<device>
<name>{name}</name>
<xml-root/>
</device>
</devices>
</config>''', 'config', 'http://tail-f.com/ns/ncs'


def output_config():
    return '''<?xml version="1.0" ?>
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


def main(args):
    json_schema = json.loads(open(args.module).read())
    schema = Schema(json_schema)

    if not args.hierarchy:
        doc, xmlroot = prepare_output(args)
        iter_schema(args, schema, xmlroot)

        output_file = open(args.output, 'w') if args.output else sys.stdout
        output_file.write(prettify(doc))
    else:
        print_schema(args, schema)


if __name__ == "__main__":
    main(parseArgs(sys.argv[1:]))
