#!/usr/bin/env python3
'''
# 2026-09-28
cd dy_live/protobuf/webcast_proto_re
rm -rf js/
rm -rf ../douyin ../proto

# Almost same as but simpler than '__federation_expose_default_export.*.js'
# wget -cP js/ https://lf3-social.iesdouyin.com/obj/douyin-social-cdn/pcim/static/js/async/4187.2096e141.js
# wget -cP js/ https://lf-webcast-platform.bytetos.com/obj/webcast-platform-cdn/webcast/douyin_live/chunks/2492.d6332b8c.js

wget -cP js/ https://lf3-social.iesdouyin.com/obj/douyin-social-cdn/pcim/static/js/async/__federation_expose_default_export.0ccd0cf4.js
wget -cP js/ https://lf-webcast-platform.bytetos.com/obj/webcast-platform-cdn/webcast/douyin_live/chunks/transport-schema-im.63ff9a29.js
wget -cP js/ https://lf-webcast-platform.bytetos.com/obj/webcast-platform-cdn/webcast/douyin_live/chunks/live-schema-im.e322bd8a.js
wget -cP js/ https://lf-webcast-platform.bytetos.com/obj/webcast-platform-cdn/webcast/douyin_live/chunks/ecom-schema-im.5ba3dfe1.js

python3 js2proto.py js/*.js
'''

# Pipeline steps:
# 1. Prepare
#    Download javascript file as schema.js
# 2. Structurize
#    1) Format schema.js with jsbeautifier
#    --> formatted.schema.js
#    2) Extract proto related snippet from the JavaScript text, arrange the snippet for easier parsing
#    --> snippet.schema.js
# 3. Parse
#    1) Parse JavaScript snippets into internal Message representation
#    2) Assemble proto files
#    --> ../proto/some/package/name.proto
# 4. Compile
#    Compile the proto files into Python with protoc
#    --> ../<PROJECT_NAME>/some/package/name_pb2.py

import argparse
import os
import re
import sys
import math
from time import time
from typing import Callable, Dict, List, Set, Tuple
from dataclasses import dataclass, field
from pprint import pprint
import shutil

PROJECT_NAME = 'douyin'

SCALAR_TYPES = {
    "int32": "int32",
    "int64": "int64",
    "int64String": "int64",
    "uint32": "uint32",
    "uint64": "uint64",
    "uint64String": "uint64",
    # https://protobuf.dev/programming-guides/proto3/#scalar
    # sint32
    # sint64
    # fixed32
    # fixed64
    # sfixed32
    # sfixed64
    "float": "float",
    "double": "double",
    "bool": "bool",
    "string": "string",
    "bytes": "bytes",
}


RE_JS_INTEGER = r'-?\d+(?:e\d+)?'
RE_JS_IDENTIFIER = r'[a-zA-Z_$][\w$]*'
RE_JS_QUOLIFIED_IDENTIFIER = r'[a-zA-Z_$][\w\.$]*'
RE_IDENTIFIER = r'[a-zA-Z_]\w*'
RE_QUOLIFIED_IDENTIFIER = r'[a-zA-Z_][\w\.]*'


def split_map_type(map_type: str):
    return map_type[4:-1].split(',', 1)


def parent_of(n: str):
    return '.'.join(n.split('.')[:-1])


def js_type_to_proto(t: str, root='', quolified=True):
    """
    js 类型 -> proto 类型

    webcast.data.PreviewExposeData.Meta.Host
        -> webcast.data.PreviewExposeData.Meta.Host
    int64String
        -> int64
    """
    if t.startswith('map<') and t.endswith('>'):  # map<string,string>
        key_type, value_type = split_map_type(t)
        return 'map<' + js_type_to_proto(key_type, root) + ',' + js_type_to_proto(value_type, root) + '>'

    if t in SCALAR_TYPES:
        return SCALAR_TYPES[t]

    parts = t.split(".")
    if root:
        parts.insert(0, root)
    return ".".join(parts) if quolified else parts[-1]


@dataclass
class Oneof:
    name: str = ""
    fields: list[str] = field(default_factory=list)


@dataclass
class Field:
    number: int = 0
    name: str = ''
    full_type: str = ''
    default: str = ''
    label_bits: int = 0
    trace: str = field(default='', compare=False)

    def __repr__(self):
        return self.compose()

    def update(self, **kwargs):
        self.__dict__.update(**kwargs)

    def compose(self, optional: bool | None = None, trace=False):
        repeated = "repeated " if (self.label_bits >> 1) & 1 else ""
        packed = " [packed = true]" if (self.label_bits >> 2) & 1 else ""
        optional_ = "optional "
        if (optional is not None) and (not optional):
            optional_ = ""
        elif repeated or self.full_type.startswith('map<'):
            optional_ = ""
        default = f" [default = {self.default}]" if self.default else ""
        trace_ = f" // from {self.trace}" if trace else ''
        return f"{repeated}{optional_}{self.full_type.replace(',',', ')} {self.name} = {self.number}{packed}{default};{trace_}"


def compose_label_bits(packed=0, repeated=0, message=0):
    return (packed << 2) + (repeated << 1) + message


class Message:
    def __init__(self, full_name: str, parent: 'Message' = None, namespace='', is_enum=False, trace=''):
        self.is_enum = is_enum
        self.full_name = full_name
        self.name = full_name.split(".")[-1]
        self.namespace = namespace
        self.parent: 'Message' = parent
        self.fields: Dict[str, 'Field'] = {}
        self.field_names: List[str] = []  # for ordering
        self.oneofs: List['Oneof'] = []
        self.children: List[str] = []
        self.trace = trace  # source file name : line number

    def rebase(self, to: 'Message', namespace: str = '', ignore_children=False):
        if len(self.children) > 0 and not ignore_children:
            raise Exception("Can't rebase children")
        self.parent.children.pop(self.parent.children.index(self.full_name))
        self.full_name = f'{to.full_name}.{self.name}' if to else self.name
        self.namespace = namespace or (to.namespace if to else '')
        self.parent = to
        to.children.append(self.full_name)

    def merge(self, m: 'Message') -> None:
        if self.is_enum != m.is_enum:
            raise Exception(f"Can't merge enum type with non enum types.")
        if self.full_name != m.full_name:
            raise Exception(f"Can't merge with different `full_name`. this={self.full_name}, that={m.full_name}.")
        fi = -1
        for fn in m.field_names:
            if fn in self.field_names:
                if self.fields[fn] != m.fields[fn]:
                    f1 = self.fields[fn].compose(False, True)
                    f2 = m.fields[fn].compose(False, True)
                    raise Exception(f"Different field definition of message `{m.full_name}`: \n    {f1}\n    {f2}")
                fi = self.field_names.index(fn)
            else:
                self.fields[fn] = m.fields[fn]
                self.field_names.insert(fi + 1, fn)  # insert after last known field from `m`
                fi += 1

        if not self.is_enum:
            numbers = [f.number for f in self.fields.values()]
            dups = '\n    '.join([f.compose(False, True)
                                 for f in self.fields.values() if numbers.count(f.number) > 1])
            if dups:
                raise Exception(f"Duplicate fields number of message `{m.full_name}`: \n    {dups}")

        self.children = list(set(self.children + m.children))
        self.trace = f'{self.trace} and/or {m.trace}'


def indent_size(s: str, blank_as_inf=False):
    s_ = s.lstrip()
    if len(s_) == 0 and blank_as_inf:
        return math.inf
    return len(s) - len(s_)


def indented_range(lines: List[str]):
    indent = indent_size(lines[0])
    for i, line in enumerate(lines[1:]):
        if indent_size(line, True) <= indent:
            break
    return i + 1  # `i` starts from lines[1:]


def find_if(lst, pred: Callable) -> int | None:
    for i, n in enumerate(lst):
        if pred(n):
            return i


def parse(root: str, text: str, source_file='') -> Dict[str, 'Message']:
    """
    Parse JavaScript snippet as a forest of Message trees
    """
    messages = {root: Message(root)}
    referenced_names = []  # full_name of messages referenced in fields

    stack = [(0, root)]
    m = None
    trace = ''
    for line in text.splitlines():
        if line.startswith(':'):
            trace = f'{source_file}:' + line[1:]
            continue
        indent = indent_size(line)
        # message name or namespace name
        #     ChatMessage
        m_ = re.match(rf"\s*({RE_IDENTIFIER})", line)
        if m_:
            name = m_.group(1)
            while stack and indent <= stack[-1][0]:
                stack.pop()
            if stack:
                parent_name = stack[-1][1]
                full_name = parent_name + "." + name
            else:
                parent_name = ''
                full_name = name

            if full_name in messages:
                # raise Exception(f"Duplicate message name: {full_name}")
                print(f"Duplicate message name: {full_name}")

            parent = messages.get(parent_name, None)

            m = Message(full_name, parent, is_enum=(' enum ' in line), trace=trace)
            messages[full_name] = m

            # for nested messages
            if parent:
                parent.children.append(full_name)

            if m.is_enum:
                pairs = [e.split('=') for e in line.split()[2:]]
                for name, value in pairs:
                    m.fields.setdefault(name, Field()).update(
                        name=name,
                        number=int(float(value)),
                        trace=trace,
                    )
                    m.field_names.append(name)

            stack.append((indent, full_name))
            continue

        if m is None:
            continue

        # message fields
        #   1: user_name string 0
        #   2: alternative_effect_config map<uint32,webcast.data.MemberMessage.EffectConfig> 0
        if ': ' in line:
            # remove the extra layer of `.decode` function
            for func_name in ['decode', 'encode']:
                if m.name == func_name and len(m.fields) == 0:
                    m = m.parent
                    messages.pop(m.full_name + '.' + func_name, None)
                    m.children = [c for c in m.children if c != m.full_name + '.' + func_name]
                    break

            number, name, ftype, label_bits = line.replace(':', '').split()
            full_type = js_type_to_proto(ftype, root)
            referenced_names.append(full_type)

            m.fields.setdefault(name, Field()).update(
                number=int(float(number)),
                name=name,
                full_type=full_type,
                label_bits=int(label_bits),
                trace=trace,
            )
            m.field_names.append(name)
            continue

        parts = line.split()

        # !typehint message_type=im_proto.MuteMessageType
        if '!typehint' == parts[0]:
            for p in parts[1:]:
                name, ftype = p.split('=', 1)
                full_type = js_type_to_proto(ftype, root)
                m_ = m.parent  # mind the right message object
                m_.fields.setdefault(name, Field()).update(full_type=full_type)

        # oneof fields
        elif '!oneof' == parts[0]:
            m.oneofs.append(Oneof(name=parts[1], fields=parts[2:]))
            continue

        elif '!default' == parts[0]:
            name, value = line.split(maxsplit=1)[1].split('=', 1)
            m.fields.setdefault(name, Field()).update(default=value)

    # invalid fields introduced by !default
    for m in messages.values():
        m.fields = {n: f for n, f in m.fields.items() if f.name}

    # enum default value to enum name
    for m in messages.values():
        for f in m.fields.values():
            if f.default and (f.full_type in messages) and messages[f.full_type].is_enum:
                e = messages[f.full_type]
                enum_name = [ef.name for ef in e.fields.values() if ef.number == int(f.default)][0]
                f.default = enum_name

    # empty messages also appear like namespaces.
    namespaces = [''] + [
        n for n, m in messages.items()
        if len(m.fields) == 0 and m.full_name not in referenced_names
    ]
    messages = {
        n: m for n, m in messages.items()
        if m.full_name not in namespaces
    }
    # remove children reference to namespaces
    for m in messages.values():
        m.children = [c for c in m.children if c not in namespaces]

    # populate namespace
    def namespace_of(m: Message):
        if m.namespace:
            return m.namespace
        if m.parent.full_name in namespaces:
            m.namespace = m.parent.full_name
            return m.namespace
        return namespace_of(m.parent)

    for m in messages.values():
        if len(m.namespace) == 0:
            m.namespace = namespace_of(m)

    return messages


def emit_message(messages: Dict[str, 'Message'], name: str, level=0, trace=False):
    m: Message = messages[name]
    pad = "  " * level
    out = []

    if trace:
        out.append(pad + f"// from {m.trace}")

    if m.is_enum:
        out.append(pad + 'enum ' + m.name + ' {')

        # proto3 enforces 0 to be the first value.
        # if not any(f.number == 0 for f in m.fields.values()):
        #     name = m.name + '_UNKNOWN'
        #     out.append(f"{pad}  {name} = 0;")

        # for f in sorted(m.fields.values(), key=lambda f: abs(f.number)):
        for f in [m.fields[n] for n in m.field_names]:
            out.append(f"{pad}  {f.name} = {f.number};")

    else:
        out.append(pad + 'message ' + m.name + ' {')
        all_oneof_fields = [n for o in m.oneofs for n in o.fields]
        # fields
        fields = [m.fields[n] for n in m.field_names if n not in all_oneof_fields]
        for f in sorted(fields, key=lambda m: m.number):
            out.append(f"{pad}  {f.compose(trace=trace)}")

        # oneof fields
        for o in m.oneofs:
            out.append(f"{pad}  oneof {o.name} {{")
            fields = [f for f in m.fields.values() if f.name in o.fields]
            for f in sorted(fields, key=lambda m: m.number):
                out.append(f"{pad}    {f.compose(optional=False,trace=trace)}")
            out.append(f"{pad}  }}")

    # nested messages
    for child in m.children:
        out.append("")
        out.extend(emit_message(messages, child, level + 1, trace))

    if len(m.children) + len(m.fields) > 0:
        out.append(pad + "}")
    else:
        out[-1] += "}"  # empty message body {}

    return out


def gather_referenced_namespaces(namespaces, messages, n: str, result: set):
    m: Message = messages[n]
    if m.is_enum:
        return
    for f in m.fields.values():
        ftype = f.full_type
        parent_name = parent_of(ftype)
        if parent_name in namespaces and parent_name != '':
            result.add(parent_name)
    for c in m.children:
        gather_referenced_namespaces(namespaces, messages, c, result)


def fuse_messages(s1: Dict[str, Message], s2: Dict[str, Message]):
    """
    Fuse messages from `s2` into `s1`
    """
    exceptions: List[Exception] = []
    for m2 in s2.values():
        if m2.full_name in s1:
            try:
                s1[m2.full_name].merge(m2)
            except Exception as e:
                exceptions.append(e)
        else:
            s1[m2.full_name] = m2
    if exceptions:
        s = '\n'.join(f"{i+1:2}: {str(e)}" for i, e in enumerate(exceptions))
        raise Exception(f"Errors while fusing messages:\n{s}")


def move_enums(messages: Dict[str, Message]):
    """
    Enum value names may conflict in global namespace
    We move definition of enums, that are referenced by only one message, into that message body.
    """
    inverted_name_ref: Dict[str, set] = {}  # full_type --> name of all messages referencing it

    def add_name_ref(full_type: str, referrer: str):
        types = split_map_type(full_type) if full_type.startswith('map<') else (full_type,)
        for t in types:
            inverted_name_ref.setdefault(t, set()).add(referrer)

    for m in messages.values():
        for f in m.fields.values():
            add_name_ref(f.full_type, m.full_name)

    for e in [*messages.values()]:
        # exactly one message references the enum type
        if e.is_enum and (e.full_name in inverted_name_ref) and (len(inverted_name_ref[e.full_name]) == 1):
            m = messages[inverted_name_ref[e.full_name].pop()]
            if e.parent.full_name == m.full_name:
                continue
            messages.pop(e.full_name)
            e.rebase(m)
            messages[e.full_name] = e
            # and update the field type
            for f in m.fields.values():
                if f.full_type in messages and messages[f.full_type].name == e.name:
                    f.full_type = e.name


def generate_proto(messages: Dict[str, Message], output_dir='../proto', quolified=False, trace=False) -> List[str]:

    namespaces = set(m.namespace for m in messages.values())

    root_message_names = []
    for m in messages.values():
        if m.parent.full_name in namespaces:
            root_message_names.append(m.full_name)

    root_message_names_by_ns: dict[str, set[str]] = {}  # ns -> message names
    for n in root_message_names:
        root_message_names_by_ns.setdefault(messages[n].namespace, set()).add(n)

    # pprint(root_message_names_by_ns)

    # do we have to import other namespaces into this namespace ?
    dependencies: dict[str, set[str]] = {}
    for ns in root_message_names_by_ns:
        dependencies.setdefault(ns, set())
        for n in root_message_names_by_ns[ns]:
            gather_referenced_namespaces(namespaces, messages, n, dependencies[ns])
        dependencies[ns] = set(ns_ for ns_ in dependencies[ns] if ns_ != ns)

    if not quolified:
        # remove namespace quolification and parent message name quolification, for readability
        def unquolify(m: Message, full_type: str):
            t = full_type.removeprefix(m.full_name + '.')
            # field type name, after unquolification, conflicts with parent message short name
            after = t.removeprefix(m.namespace + '.')
            if (after != m.name) or (full_type == m.full_name):
                t = after
            return t

        for m in messages.values():
            for f in m.fields.values():
                if f.full_type.startswith('map<'):
                    key_type, value_type = split_map_type(f.full_type)
                    f.full_type = f'map<{key_type},{unquolify(m, value_type)}>'
                else:
                    f.full_type = unquolify(m, f.full_type)

    files: dict[str, list[str]] = {}  # file name --> content lines

    for n in root_message_names:
        ns = messages[n].namespace
        fname = f"{output_dir}/{ns.replace('.', '/')}.proto"
        if fname not in files:
            imports = [f"import '{ns_.replace('.', '/')}.proto';" for ns_ in dependencies[ns]]
            if imports:
                imports.insert(0, '')  # empty line for formatting
            files[fname] = [
                '// syntax = "proto3"; // Leave syntax version to the protobuf compiler.',
                f'package {ns};',
                *imports,
                '',
            ]
        files[fname].extend(emit_message(messages, n, trace=trace))
        files[fname].append("")

    for f in files:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        write_stderr(f"Writing {f}\n")
        write_file(f, '\n'.join(files[f]))

    return list(files.keys())


def format_javascript(text: str, indent=4) -> str:
    start_time = time()
    if len(text) > 1024 * 1024:
        write_stderr(
            f"Formatting JavaScript text of length {int(len(text)/1024)} KiB, this may take some time.\n")

    import jsbeautifier as jsb
    opts = jsb.BeautifierOptions({
        "indent_size": 4,
        "indent_char": ' ',
        "preserve_newlines": True,
        "max_preserve_newlines": 1,
        "end_with_newline": True,
        "max_char": 32768,
        # ["collapse", "expand", "end-expand", "none", "preserve-inline"]
        "brace_style": 'collapse',
        "break_chained_methods": False,
        "space_in_paren": False,
        "keep_array_indentation": False,  # Why ?
    })
    text = text.replace('),', '),\n').replace('},', '},\n')
    text = text.replace(',(', ',\n(').replace(',{', ',\n{')
    text, _ = re.subn(rf',({RE_QUOLIFIED_IDENTIFIER}=function\(\))', r',\n\1', text)
    text = jsb.beautify(text, opts)

    if time() - start_time > 3:
        elapsed = time() - start_time
        write_stderr(
            f"  -- took {math.ceil(elapsed)}s. {round(len(text)/1024/elapsed)}KiB/s\n")
    return text


def js_snippet_extract_number(s: str) -> str:
    s = s.lstrip()
    # case N:
    m = re.search(rf"case\s+({RE_JS_INTEGER}):", s)
    if m:
        return m.group(1)
    # ( t >>> 3 === N )
    m = re.match(r"^[^(]*\(([^)]+)\)", s)
    if m and ('==' in m.group(0)):

        expr = m.group(1).replace(' ', '')
        parts = re.split(r"===?", expr)

        if len(parts) > 0 and re.fullmatch(RE_JS_INTEGER, parts[0]):
            return parts[0]

        if len(parts) > 1 and re.fullmatch(RE_JS_INTEGER, parts[1]):
            return parts[1]

    raise Exception(f"Not found expected number in string:\n    {s}")


def js_snippet_normalize_refname(n: str) -> str:
    """
    e.int32 --> int32
    e.live.SomeMessage.decode --> live.SomeMessage
    """
    if n.startswith('map<'):
        key_type, value_type = split_map_type(n)
        key_type = js_snippet_normalize_refname(key_type)
        value_type = js_snippet_normalize_refname(value_type)
        return f"map<{key_type},{value_type}>"
    else:
        return n.split('.', 1)[1].removesuffix('.decode')


# [e[3] = "SEND_SUCCEED"] = 3, ...
RE_ENUM_PATTERN = rf'\[{RE_JS_IDENTIFIER}\[{RE_JS_INTEGER}\] = "({RE_JS_IDENTIFIER})"\] = ({RE_JS_INTEGER})'


def js_snippet_extract_enum_body(s) -> str:
    enum_elements = re.findall(RE_ENUM_PATTERN, s)
    return " ".join([f"{e[0]}={e[1]}" for e in enum_elements])


RE_FIELD_DEFINITION = rf'({RE_JS_INTEGER}): \["({RE_IDENTIFIER})", ({RE_QUOLIFIED_IDENTIFIER}), (\d+)\]'


def extract_js_snippet_of_proto_1(text: str) -> Tuple[str, str]:
    """
    Example JavaScript:
    e.AudioChatMessage = function() {
        return s(e, {
                common: null,
                user: null,
                content: "",
            }),
            e.decode = function(e, t) {
                for (var ...,
                        a = {
                            1: ["common", r.webcast.im.Common.decode, 1],
                            2: ["user", r.webcast.data.User.decode, 1],
                            3: ["content", e.string, 0],
    ...

    Example Output:
    AudioChatMessage
            decode
                            1: ["common", webcast.im.Common, 1],
                            2: ["user", webcast.data.User, 1],
                            3: ["content", string, 0],
    """
    result: List[str] = []
    indent = ""

    lines = text.splitlines()

    # find pbjs --root name
    root = 'default'
    for i, line in enumerate(lines):
        if line.count('.roots.') == 2:
            m = re.search(r'\.roots\.(\w+)', line)
            if m:
                root = m.group(1)
                break
    if i == len(lines) - 1:
        raise Exception("Not a recognized structure of code: not found root name.")
    offset, lines = i, lines[i:]

    for i, line in enumerate(lines[:-1]):
        if '.fromBits' in lines[i] and '.fromBits' in lines[i + 1]:
            break
    if i == len(lines[:-1]) - 1:
        raise Exception("Not a recognized structure of code.")

    i += 2
    lines = lines[i:i + indented_range(lines[i:])]
    offset += i

    def append_line(s: str):
        result.append(':' + str(offset + i + 1))
        result.append(s)

    # top level namespace name
    m = re.match(rf'\s+\w+ = \w+\.({RE_IDENTIFIER}) = ', lines[0])
    if m is None:
        raise Exception("Not a recognized structure of code: not found top level namespace name")
    append_line(' ' + m.group(1))

    pattern = re.compile(
        rf'('
        rf'^(return )?{RE_IDENTIFIER}\.(?P<fn>{RE_IDENTIFIER}) = function\('
        rf'|^{RE_QUOLIFIED_IDENTIFIER} === \w\.emptyObject'
        rf'|(?P<oneof>\.oneOfGetter)'
        rf'|^(?P<field>{RE_FIELD_DEFINITION})'
        rf'|(?P<enum>{RE_ENUM_PATTERN})'
        rf')'
    )

    for i, line in enumerate(lines):
        m = pattern.search(line.lstrip())
        if m is None:
            continue

        line = line.replace('return ', '    ')
        indent = ' ' * indent_size(line)
        func_name = m.group('fn')

        # message name
        if func_name:
            append_line(f'{indent}{func_name}')

        # field of type map<>
        elif '.emptyObject' in line:
            field = line.split()[0].split('.')[1]
            ftype = 'map<>'

            snippet_lines = lines[i:i + 15]
            for j, l in enumerate(snippet_lines):
                if ' switch ' in l and ' case 1:' in snippet_lines[j + 1]:
                    key_type = re.search(rf'= ({RE_QUOLIFIED_IDENTIFIER})\(', snippet_lines[j + 2]).group(1)
                    value_type = re.search(rf'= ({RE_QUOLIFIED_IDENTIFIER})\(', snippet_lines[j + 5]).group(1)
                    key_type = js_snippet_normalize_refname(key_type)
                    value_type = js_snippet_normalize_refname(value_type)
                    ftype = f"map<{key_type},{value_type}>"
                    break

            append_line(f'{indent}    {js_snippet_extract_number(lines[i-1])}: {field} {ftype} 0')

        # oneof
        elif m.group('oneof') and ('Object.defineProperty' in lines[i - 1]) and ('.oneOfSetter' in lines[i + 1]):
            field = lines[i - 1].split('"')[1]
            oneof_fields = re.findall(rf'"({RE_IDENTIFIER})"', lines[i])
            append_line(f"{indent}!oneof {field} {' '.join(oneof_fields)}")

        # plain field
        elif m.group('field'):
            m = re.search(RE_FIELD_DEFINITION, line)
            if not m:
                raise Exception(f"Unrecognized code structure. At line:\n{lines[i]}")
            number, name, ftype, label = m.groups()
            ftype = js_snippet_normalize_refname(ftype)
            append_line(f"{indent}{number}: {name} {ftype} {label}")

        # enum definition
        elif m.group('enum'):
            # case 1
            if 'Object.create' in line:
                name = line.rsplit('.', maxsplit=1)[1].split()[0]
                append_line(f"{indent}{name} enum " + js_snippet_extract_enum_body(line))
            # case 2
            elif ('return' in lines[i]) and ('= function()' in lines[i - 3]):
                result[-1] += f" enum " + js_snippet_extract_enum_body(line)

    return root, "\n".join(result)


def extract_js_snippet_of_proto_2(text: str) -> Tuple[str, str]:
    """
    Example JavaScript:
        s.ParticipantsPage = function() {
            e.decode = function(e, t, n) {
                for (...) {
                    switch (t >>> 3) {
                        case 1:
                            r.participants && r.participants.length || (r.participants = []),
                                r.participants.push(ov.im_proto.Participant.decode(e, e.uint32()));
                            break;
                        case 2:
                            r.has_more = e.bool();
                            break;
                        case 3:
                            r.cursor = e.int64();
                            break;
                    }
                }
            }
        }

    Example Output:
        ParticipantsPage
            decode
                1: participants im_proto.Participant 3
                2: has_more bool 0
                3: cursor int64 0
    """
    result: List[str] = []
    indent = ""

    lines = text.splitlines()

    # find pbjs --root name
    root_var, root = '', 'default'
    for i, line in enumerate(lines):
        if line.count('.roots.') == 2:
            m = re.search(r'(\w+) = \w+\.roots\.(\w+)', line)
            if m:
                root_var, root = m.group(1), m.group(2)
                break
    if i == len(lines) - 1:
        raise Exception("Not a recognized structure of code: not found root name.")

    while i + 1 < len(lines) and indent_size(lines[i]) == indent_size(lines[i + 1]):
        i += 1

    lines = lines[i:i + indented_range(lines[i:])]
    offset = i

    def append_line(s: str):
        result.append(':' + str(offset + i + 1))
        result.append(s)

    # find top level namespace name
    for line in lines:
        m = re.search(rf'\b{root_var}\.({RE_JS_IDENTIFIER}) = (?:{RE_IDENTIFIER}|\()', line)
        if m:
            append_line(' ' + m.group(1))  # zero indentation is reserved for the root namespace
            break

    # Pattern to match message names, enum related lines
    #    e.SomeMessage = function() {
    #    [d[0] = "SUCCESS"] = 0, ...
    #    e.prototype.conversation_type = 1, ...
    pattern = re.compile(
        rf'('
        rf'^(return )?{RE_IDENTIFIER}\.(?P<fn>{RE_IDENTIFIER}) = function\('
        rf'|(?P<enum>{RE_ENUM_PATTERN})'
        rf'|^(?P<field_default>return \w+\.prototype\.)'
        rf')'
    )

    i = 0
    while i + 1 < len(lines):
        i += 1
        line = lines[i]
        m = pattern.search(line.lstrip())
        if m is None:
            continue

        line = line.replace('return ', '    ')
        indent = ' ' * indent_size(line)
        func_name = m.group('fn')

        # possibly message name
        if func_name:
            append_line(f'{indent}{func_name}')

            # fields
            def append(number: str, name: str, ftype: str, packed=0, repeated=0, message=0):
                message = int(message or ftype.endswith('.decode'))
                name = name.split('.', 1)[1]
                ftype = js_snippet_normalize_refname(ftype)
                bits = compose_label_bits(packed, repeated, message)
                append_line(f"{indent}    {number}: {name} {ftype} {bits}")

            def extract_field(n: str, block: List[str]):
                m = re.search(rf'({RE_QUOLIFIED_IDENTIFIER}) = ({RE_QUOLIFIED_IDENTIFIER})\(', block[0].lstrip())
                if m:
                    append(n, m.group(1), m.group(2), repeated=0)
                    return
                # repeated field
                m = re.search(rf'({RE_QUOLIFIED_IDENTIFIER})\.push\(({RE_QUOLIFIED_IDENTIFIER})\(', block[-2].lstrip())
                if m:
                    append(n, m.group(1), m.group(2), repeated=1)
                    return
                # map<> field
                m = re.search(rf'({RE_QUOLIFIED_IDENTIFIER}) === \w+\.emptyObject', block[0].lstrip())
                if m:
                    ftype = 'map<>'
                    for k, l in enumerate(block):
                        if ' switch ' in block[k] and ' case 1:' in block[k + 1]:
                            key_type = re.search(rf'= ({RE_QUOLIFIED_IDENTIFIER})\(', block[k + 2]).group(1)
                            value_type = re.search(rf'= ({RE_QUOLIFIED_IDENTIFIER})\(', block[k + 5]).group(1)
                            ftype = f"map<{key_type},{value_type}>"
                            break
                    append(n, m.group(1), ftype)
                    return

            if func_name == 'decode':
                func_block = lines[i:i + indented_range(lines[i:])]
                j = find_if(func_block, lambda l: l.startswith(indent + (' ' * 2 * 4) + 'switch '))

                if j is None:  # no `switch` block ? locate the sole field member
                    j = find_if(func_block, lambda l: indent_size(l) == len(indent) + 2 * 4 and '>>> 3 ==' in l)
                    if j is not None:
                        i += j
                        block = func_block[j:j + indented_range(func_block[j:]) + 1]  # +1 for repeated field
                        if ' ? ' in block[0]:
                            number = js_snippet_extract_number('(' + block[0].split(' ? ')[0] + ')')
                        else:
                            number = js_snippet_extract_number(block[0])
                        extract_field(number, block)
                    continue
                i += j

                # parse the whole `switch` block
                switch_block = lines[i:i + indented_range(lines[i:])]
                i0 = i  # `i0` stays here
                while i - i0 + 1 < len(switch_block):
                    i += 1
                    if ' case ' not in switch_block[i - i0]:
                        continue
                    number = js_snippet_extract_number(switch_block[i - i0])
                    case_block = switch_block[i - i0:i - i0 + indented_range(switch_block[i - i0:])]
                    extract_field(number, case_block[1:])
                    i += len(case_block) - 1  # mostly next `case`

            # enum reference
            elif func_name == 'toObject':
                func_block = lines[i:i + indented_range(lines[i:])]
                i0 = i
                while i - i0 + 1 < len(func_block):
                    i += 1
                    if '.enums === String ?' not in func_block[i - i0]:
                        continue
                    m = re.search(rf' ({RE_QUOLIFIED_IDENTIFIER})\[({RE_QUOLIFIED_IDENTIFIER})\]', func_block[i - i0])
                    if m:
                        enum_type = js_snippet_normalize_refname(m.group(1))
                        field_name = js_snippet_normalize_refname(m.group(2))
                        append_line(f'{indent}    !typehint {field_name}={enum_type}')

        # enum definition
        elif m.group('enum'):
            # case 1
            if 'Object.create' in line:
                name = line.rsplit('.', maxsplit=1)[1].split()[0]
                append_line(f"{indent}{name} enum " + js_snippet_extract_enum_body(line))
            # case 2
            elif ('return' in lines[i]) and ('= function()' in lines[i - 3]):
                result[-1] += f" enum " + js_snippet_extract_enum_body(line)

        # field default value
        elif m.group('field_default'):
            pairs = re.findall(rf'\.prototype\.({RE_IDENTIFIER}) = ("[^"]+"|{RE_JS_INTEGER})', line)
            for name, value in pairs:
                if value != '0':
                    append_line(f"{indent}    !default {name}={value}")

    return root, "\n".join(result)


def compile_proto(files: str, include_path='.'):
    write_stderr(f"Compiling {len(files)} proto files\n")

    from subprocess import run

    start_time = time()

    output_path = f'../{PROJECT_NAME}'
    os.makedirs(output_path, exist_ok=True)
    run(
        [
            "protoc",
            "-I", include_path,
            f"--python_out={output_path}",
            *files,
        ],
        check=True,
    )
    run(
        [
            "protol",
            "--in-place",
            # "--create-package",
            f"--python-out={output_path}",
            "protoc",
            f"--proto-path={include_path}",
            *files,
        ],
        check=True,
    )
    write_stderr(f"  -- took {round(time() - start_time, 1)}s\n")


def read_file(file_path: str) -> str:
    with open(file_path, 'r', encoding="utf8") as f:
        return f.read()


def write_file(file_path: str, text: str, append=False) -> None:
    with open(file_path, 'a' if append else 'w', encoding='utf8') as f:
        f.write(text)


def write_stderr(text: str):
    sys.stderr.write(text)
    sys.stderr.flush()


def choose_extractor(text: str) -> Callable:
    def has_match(pattern):
        try:
            it = re.finditer(pattern, text)
            next(it)
            return True
        except BaseException:
            return False
    if has_match(RE_FIELD_DEFINITION):
        return extract_js_snippet_of_proto_1
    else:
        return extract_js_snippet_of_proto_2


def main(args):
    messages: Dict[str, Message] = {}

    for f in args.files:
        basename = os.path.basename(f)

        if os.path.exists(f"formatted.{basename}") and \
                os.stat(f).st_ctime < os.stat(f"formatted.{basename}").st_ctime:
            print(f"Using 'formatted.{basename}'")
            text = read_file(f"formatted.{basename}")
        else:
            text = format_javascript(read_file(f), indent=4)
            write_file(f"formatted.{basename}", text)

        root, text = choose_extractor(text)(text)
        write_file(f"snippet.{basename}", text)

        # fusing is meaningless for now, we take it as a method of conflict detetion instead.
        fuse_messages(messages, parse(root, text, f"formatted.{basename}"))

    move_enums(messages)

    files = generate_proto(messages, output_dir='../proto', quolified=args.quolify, trace=args.trace)

    compile_proto(files, include_path='../proto')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate proto files and compiled Python protobuf from JavaScript schema snapshots.')
    parser.add_argument('--quolify', action='store_true', help='Use fully quolified type name in fields definition.')
    parser.add_argument('--trace', action='store_true', help='Enable proto trace output.')
    parser.add_argument('files', nargs='+', help='Input JavaScript schema files.')
    args = parser.parse_args()

    main(args)
