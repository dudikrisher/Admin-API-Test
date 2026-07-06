import json, re, sys, os

# Usage: python3 postman_to_openapi_generator.py [output.json] [postman_collection.json]
# Defaults: reads  <this folder>/Admin_API.postman_collection.json
#           writes <repo>/docs/openapi.json
BASE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'Admin_API.postman_collection.json')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(os.path.join(BASE, '..', 'docs', 'openapi.json'))

with open(SRC, encoding='utf-8') as f:
    data = json.load(f)

INT_STR_PATTERN = r'^-?[0-9]+$'
DEC_STR_PATTERN = r'^-?[0-9]+(\.[0-9]+)?$'
STOPWORDS = {'If','Note','The','This','See','Refer','In','When','For','On','At','All','Else'}
PRIMITIVES = {'string','int','decimal','boolean','bool','enum','char','date','unix','integer','number'}

def clean_field_name(raw):
    s = raw.replace('<br>', ' ').replace('\\>', '>').replace('\\', '')
    s = re.sub(r'`?\(?\[?NEW\s*v?[\d.]*\]?\)?`?', '', s)
    s = re.sub(r'`?\(?\[?CHANGED\s*v?[\d.]*\]?\)?`?', '', s)
    s = re.sub(r'`(optional|mandatory)`', '', s, flags=re.I)
    s = s.replace('**', '').replace('`', '')
    s = s.strip(' *_~>').strip()
    m = re.match(r'^([a-zA-Z][a-zA-Z0-9_]*)\s*(optional|mandatory)?$', s, flags=re.I)
    return m.group(1) if m else s

def clean_desc(raw):
    s = raw.replace('<br>', '\n')
    s = s.replace('\\[', '[').replace('\\]', ']').replace('\\-', '-').replace('\\*', '*')
    s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)
    s = s.replace('**', '').replace('~~', '')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n\s*\n+', '\n', s)
    return s.strip()

def strip_version_markers(text):
    text = re.sub(r'`\(?\[?NEW\s*v?[\d.]*\]?\)?`\s*', '', text)
    text = re.sub(r'\(NEW\s*v?[\d.]+\)\s*', '', text)
    text = re.sub(r'\[NEW\s*v?[\d.]+\]\s*', '', text)
    text = re.sub(r'`NEW`\s*', '', text)
    return text

def extract_enum(desc):
    d = strip_version_markers(desc)
    m = re.search(r'(?:Allowed|Available) values:\s*\n(.*)', d, flags=re.S | re.I)
    if m:
        vals, meanings, abandoned = [], {}, False
        for line in m.group(1).split('\n'):
            line = line.strip().lstrip('-*\u2022 ').strip()
            if not line: continue
            mm2 = re.match(r'^([A-Za-z][A-Za-z0-9_]*)\s*([-:=(\u2013\u2014].*)?$', line)
            if mm2:
                tok, rest = mm2.group(1), (mm2.group(2) or '')
                if tok in STOPWORDS and rest: break
                if tok not in vals: vals.append(tok)
                rest = rest.strip(' -:=\u2013\u2014')
                rest = re.sub(r'^\(|\)$', '', rest).strip()
                if rest and tok not in meanings: meanings[tok] = rest
            else:
                first = line.split()[0]
                if first in STOPWORDS or first[0].islower(): break
                abandoned = True; break
        if abandoned: return None, desc
        if 2 <= len(vals) <= 12:
            new_desc = d[:m.start()].strip()
            if meanings:
                lines = [f"- {k} \u2014 {v}" for k, v in meanings.items()]
                new_desc = ((new_desc + '\n\n') if new_desc else '') + '\n'.join(lines)
            return vals, new_desc
    m = re.search(r'(?:Allowed|Available) values:\s*([^\n.]+)', d, flags=re.I)
    if m:
        raw_tokens = re.split(r',|\band\b|&', m.group(1))
        vals, ok = [], True
        for t in raw_tokens:
            t = strip_version_markers(t).strip(' `.,')
            if not t: continue
            if re.match(r'^[A-Za-z][A-Za-z0-9_]*$', t):
                if t not in vals: vals.append(t)
            else:
                ok = False; break
        if ok and 2 <= len(vals) <= 12:
            new_desc = (d[:m.start()].rstrip(' ,') + ' ' + d[m.end():]).strip(' .,\n')
            return vals, re.sub(r'[ \t]+', ' ', new_desc).strip()
    codes = re.findall(r'(?:^|\n)\s*([A-Z])\s*=\s*([A-Za-z][^\n]*)', d)
    if len(codes) >= 2:
        vals, meanings = [], {}
        for c, mng in codes:
            if c not in vals:
                vals.append(c); meanings[c] = mng.strip()
        if 2 <= len(vals) <= 12:
            prefix = re.split(r'\n\s*[A-Z]\s*=', d)[0].strip()
            lines = [f"- {k} \u2014 {v}" for k, v in meanings.items()]
            return vals, ((prefix + '\n\n') if prefix else '') + '\n'.join(lines)
    words = re.findall(r'(?:^|\n)\s*([A-Z][A-Za-z_0-9]+):\s+([^\n]+)', d)
    if len(words) >= 2:
        vals, meanings = [], {}
        for w, mng in words:
            if w in STOPWORDS: continue
            if w not in vals:
                vals.append(w); meanings[w] = mng.strip()
        if 2 <= len(vals) <= 12:
            prefix = re.split(r'\n?\s*[A-Z][A-Za-z_0-9]+:\s', d)[0].strip()
            lines = [f"- {k} \u2014 {v}" for k, v in meanings.items()]
            return vals, ((prefix + '\n\n') if prefix else '') + '\n'.join(lines)
    return None, desc

def bounded_int_pattern(n):
    if n < 10: return f'^[0-{n}]$'
    if n == 10: return r'^([0-9]|10)$'
    if n < 20: return f'^([0-9]|1[0-{n-10}])$'
    return None

def parse_minmax(desc):
    mm = {}
    m = re.search(r'Max value:\s*(\d+)', desc, flags=re.I)
    if m: mm['max'] = int(m.group(1))
    m = re.search(r'Min value:\s*(\d+)', desc, flags=re.I)
    if m: mm['min'] = int(m.group(1))
    return mm

def is_separator(line):
    line = line.strip()
    if not line.startswith('|'): return False
    cells = [c.strip() for c in line.strip('|').split('|')]
    return all(re.match(r'^:?-+:?$', c) for c in cells if c) and len(cells) >= 1

NESTED_RE = re.compile(r'^\s*(\*\*)?\s*\\?>')

def parse_all_tables(text):
    tables = []
    if not text: return tables
    lines = text.split('\n')
    optional_section = False
    current = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        low = stripped.lower()
        if 'optional field' in low: optional_section = True
        elif 'mandatory field' in low: optional_section = False
        if not stripped.startswith('|'):
            current = None
            continue
        if i + 1 < len(lines) and is_separator(lines[i+1]):
            header = [c.strip().lower() for c in stripped.strip('|').split('|')]
            current = {'header': header, 'rows': [], 'optional_default': optional_section}
            tables.append(current)
            continue
        if is_separator(stripped): continue
        if current is not None:
            current['rows'].append([c.strip() for c in stripped.strip('|').split('|')])
    return tables

def row_to_entry(cells, optional_default):
    raw_name = cells[0]
    if '~~' in raw_name or 'REMOVED' in raw_name.upper():
        return None
    nested = bool(NESTED_RE.match(raw_name))
    fname = clean_field_name(raw_name)
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', fname):
        return None
    is_optional = optional_default or bool(re.search(r'`optional`', raw_name, flags=re.I))
    if len(cells) >= 3:
        ftype, fdesc = clean_desc(cells[1]), clean_desc(' '.join(cells[2:]))
    else:
        ftype, fdesc = '', clean_desc(cells[1])
    if re.match(r'^\s*optional\b', fdesc, flags=re.I): is_optional = True
    if re.search(r'\bMandatory if\b', fdesc, flags=re.I): is_optional = True
    return {'name': fname, 'type': ftype, 'description': fdesc, 'optional': is_optional, 'nested': nested, 'children': {}}

def field_tables(tables):
    return [t for t in tables if t['header'] and t['header'][0] in ('field', 'parameter', 'name')]

def parse_field_map(text):
    fields = {}
    for t in field_tables(parse_all_tables(text)):
        current_parent = None
        for cells in t['rows']:
            if len(cells) < 2: continue
            e = row_to_entry(cells, t['optional_default'])
            if not e: continue
            fname = e['name']
            if e['nested']:
                if current_parent and current_parent in fields:
                    fields[current_parent]['children'][fname] = e
                if fname not in fields:
                    fields[fname] = dict(e, children={})
            else:
                if fname not in fields:
                    fields[fname] = e
                tnorm = (e['type'] or '').replace(' ', '').lower()
                current_parent = fname if ('list' in tnorm or '[]' in tnorm) else None
    return fields

def custom_array_base(ftype):
    t = strip_version_markers(ftype or '').replace('\\', '').strip()
    m = re.match(r'^([A-Za-z][A-Za-z0-9_]*)\s*\[\s*\]$', t)
    if m and m.group(1).lower() not in PRIMITIVES:
        return m.group(1)
    return None

def openapi_type(table_type):
    t_orig = (table_type or '')
    t = t_orig.replace(' ', '').replace('\\', '').lower()
    if not t: return None
    is_array = '[]' in t or t.startswith('list') or t == 'list'
    base = None
    if 'intstring' in t or 'stringified' in t:
        base = {"type": "string", "pattern": INT_STR_PATTERN}
    elif 'decimalstring' in t:
        base = {"type": "string", "format": "decimal", "pattern": DEC_STR_PATTERN}
    elif 'hh:mm:ss' in t:
        base = {"type": "string", "pattern": r'^\d{2}:\d{2}:\d{2}$'}
    elif 'hh:mm' in t:
        base = {"type": "string", "pattern": r'^\d{2}:\d{2}$'}
    elif 'yyyy-mm-dd' in t or t == 'date':
        base = {"type": "string", "format": "date"}
    elif 'unix' in t:
        base = {"type": "integer", "format": "int64"}
    elif 'string' in t or 'enum' in t or 'char' in t:
        base = {"type": "string"}
    elif re.search(r'\bint\b', t_orig.lower()) or 'integer' in t:
        base = {"type": "integer"}
    elif t == 'decimal' or 'number' in t:
        base = {"type": "number"}
    elif 'bool' in t:
        base = {"type": "boolean"}
    if is_array:
        return {"type": "array", "items": base or {"type": "object"}}
    return base

def apply_constraints_and_desc(sch, desc):
    mm = parse_minmax(desc)
    if mm:
        if sch.get('type') in ('integer', 'number'):
            if 'max' in mm: sch['maximum'] = mm['max']
            if 'min' in mm: sch['minimum'] = mm['min']
        elif sch.get('type') == 'string' and sch.get('pattern') == INT_STR_PATTERN and 'max' in mm:
            bp = bounded_int_pattern(mm['max'])
            if bp: sch['pattern'] = bp
            sch['x-max-value'] = mm['max']
        desc = re.sub(r'\.?\s*(Max|Min) value:\s*\d+\.?', '', desc, flags=re.I).strip(' .\n')
    m = re.search(r'Max length\s*[-:]?\s*(\d+)', desc, flags=re.I)
    if m: sch['maxLength'] = int(m.group(1))
    m = re.search(r'\((\d+)\s*chars?\s*\)', desc)
    if m: sch['maxLength'] = int(m.group(1))
    if desc:
        sch['description'] = desc
    else:
        sch.pop('description', None)
    return sch

def entry_to_schema(entry, ref_overrides=None):
    name = entry['name']
    if ref_overrides and name in ref_overrides:
        return {"$ref": ref_overrides[name]}
    sch = openapi_type(entry['type']) or {"type": "string"}
    desc = entry.get('description') or ''
    if desc:
        enum, desc = extract_enum(desc)
        if enum:
            target = sch['items'] if sch.get('type') == 'array' and sch.get('items', {}).get('type') in (None, 'string') else sch
            if target.get('type') in (None, 'string'):
                target.pop('pattern', None)
                target['type'] = 'string'
                target['enum'] = enum
    return apply_constraints_and_desc(sch, desc)

def build_model_from_tables(tables, ref_overrides=None):
    ftabs = field_tables(tables)
    if not ftabs:
        return None
    ptr = {'i': 1}
    def process_table_into(table, props, required):
        current_parent = None
        for cells in table['rows']:
            if len(cells) < 2: continue
            e = row_to_entry(cells, table['optional_default'])
            if not e: continue
            fname = e['name']
            if e['nested']:
                base = custom_array_base(e['type'])
                if base and ptr['i'] < len(ftabs):
                    sub_table = ftabs[ptr['i']]; ptr['i'] += 1
                    sub_props, sub_req = {}, []
                    process_table_into(sub_table, sub_props, sub_req)
                    sub_schema = {"type": "object", "properties": sub_props}
                    if sub_req: sub_schema['required'] = sub_req
                    sch = {"type": "array", "items": sub_schema}
                    sch = apply_constraints_and_desc(sch, e['description'])
                else:
                    sch = entry_to_schema(e, ref_overrides)
                if current_parent and current_parent in props:
                    parent_sch = props[current_parent]
                    target = parent_sch.get('items', parent_sch)
                    if target.get('type') == 'object':
                        target.setdefault('properties', {})[fname] = sch
                continue
            base = custom_array_base(e['type'])
            tnorm = (e['type'] or '').replace(' ', '').lower()
            if base and ptr['i'] < len(ftabs):
                sub_table = ftabs[ptr['i']]; ptr['i'] += 1
                sub_props, sub_req = {}, []
                process_table_into(sub_table, sub_props, sub_req)
                sub_schema = {"type": "object", "properties": sub_props}
                if sub_req: sub_schema['required'] = sub_req
                sch = {"type": "array", "items": sub_schema}
                sch = apply_constraints_and_desc(sch, e['description'])
                current_parent = None
            elif 'list' in tnorm and '[]' not in tnorm:
                sch = {"type": "array", "items": {"type": "object", "properties": {}}}
                sch = apply_constraints_and_desc(sch, e['description'])
                props[fname] = sch
                current_parent = fname
                if fname != 'id' and not e['optional']:
                    required.append(fname)
                continue
            else:
                sch = entry_to_schema(e, ref_overrides)
                current_parent = None
            props[fname] = sch
            if fname == 'id':
                if '$ref' not in sch:
                    sch['readOnly'] = True
            elif not e['optional']:
                required.append(fname)
    props, required = {}, []
    process_table_into(ftabs[0], props, required)
    while ptr['i'] < len(ftabs):
        t = ftabs[ptr['i']]; ptr['i'] += 1
        process_table_into(t, props, required)
    out = {"type": "object", "properties": props}
    if required:
        out['required'] = required
    return out

def build_lookup_enums(instr_desc):
    tables = parse_all_tables(instr_desc)
    comps = {}
    for t in tables:
        h = t['header']
        if h[:2] == ['category', 'category api']:
            vals, lines = [], []
            for r in t['rows']:
                if len(r) >= 2 and re.match(r'^[A-Z]$', r[1].strip()):
                    code, name = r[1].strip(), clean_desc(r[0])
                    if code not in vals:
                        vals.append(code); lines.append(f"{code} \u2014 {name}")
            comps['InstrumentCategory'] = {"type": "string", "enum": vals,
                "description": "Instrument category:\n\n" + "\n".join(f"- {l}" for l in lines)}
        elif len(h) >= 3 and h[0] == 'category' and 'subcategory api' in h[-1]:
            vals, lines = [], []
            for r in t['rows']:
                if len(r) >= 3:
                    code = strip_version_markers(r[-1]).strip()
                    if re.match(r'^[A-Z]$', code):
                        cat, name = clean_desc(strip_version_markers(r[0])), clean_desc(strip_version_markers(r[1]))
                        if code not in vals: vals.append(code)
                        lines.append(f"{code} \u2014 {name} (category: {cat})")
            comps['InstrumentSubCategory'] = {"type": "string", "enum": vals,
                "description": "Instrument sub category. Valid values depend on the selected category:\n\n" + "\n".join(f"- {l}" for l in lines)}
        elif len(h) >= 4 and h[0] == 'category' and 'underlyingassets api' in h[-1]:
            vals, seen_pairs, lines = [], set(), []
            for r in t['rows']:
                if len(r) >= 4:
                    code = strip_version_markers(r[-1]).strip()
                    if re.match(r'^[A-Z]$', code):
                        name = clean_desc(strip_version_markers(r[2]))
                        if code not in vals: vals.append(code)
                        if (code, name) not in seen_pairs:
                            seen_pairs.add((code, name)); lines.append(f"{code} \u2014 {name}")
            comps['InstrumentUnderlyingAssets'] = {"type": "string", "enum": vals,
                "description": "Instrument underlying assets type. Applicability depends on category/subCategory:\n\n" + "\n".join(f"- {l}" for l in lines)}
    return comps

def url_to_path_g(url):
    path = re.sub(r'\{\{URL_ORIGIN\}\}', '', url).split('?')[0]
    path = re.sub(r':([a-zA-Z_][a-zA-Z0-9_]*)', r'{\1}', path)
    path = re.sub(r'/mps/\d+/api-keys/[a-f0-9-]+', '/mps/{mpId}/api-keys/{apiKey}', path)
    path = re.sub(r'/mps/\d+/api-keys', '/mps/{mpId}/api-keys', path)
    path = re.sub(r'/mps/\d+', '/mps/{mpId}', path)
    path = re.sub(r'/mp-groups/\d+/api-keys/[a-f0-9-]+', '/mp-groups/{groupId}/api-keys/{apiKey}', path)
    path = re.sub(r'/mp-groups/\d+/api-keys', '/mp-groups/{groupId}/api-keys', path)
    path = re.sub(r'/mp-groups/\d+', '/mp-groups/{groupId}', path)
    for res in ['cbrs','tick-sizes','calendars','instruments','instrument-groups']:
        path = re.sub(rf'/{res}/\d+', f'/{res}/{{id}}', path)
    return path or '/'

def safe_json(raw):
    try: return json.loads(raw)
    except: return None

def merge_schemas(a, b):
    if a.get('type') == 'object' and b.get('type') == 'object':
        props = dict(a.get('properties', {}))
        for k, v in b.get('properties', {}).items():
            props[k] = merge_schemas(props[k], v) if k in props else v
        return {"type": "object", "properties": props}
    if a.get('type') == 'array' and b.get('type') == 'array':
        ai, bi = a.get('items', {}), b.get('items', {})
        return {"type": "array", "items": merge_schemas(ai, bi) if ai and bi else (ai or bi)}
    return a

def fm_get(fm, key):
    if key in fm: return fm[key]
    kl = key.lower()
    for k, v in fm.items():
        if k.lower() == kl: return v
    return None

def enrich_property(sch, value, info, name=None):
    if name and (name.lower() == 'email' or name.lower().endswith('email')):
        if not isinstance(value, (dict, list)):
            sch = {**sch, "type": "string", "format": "email"}
    if not info: return sch
    if not isinstance(value, (dict, list)):
        mapped = openapi_type(info['type'])
        if mapped and mapped.get('type') != 'array':
            sch = {**sch, **mapped}
    elif isinstance(value, list):
        mapped = openapi_type(info['type'])
        if mapped and mapped.get('type') == 'array' and isinstance(sch.get('items'), dict) and sch['items'].get('type') == mapped['items'].get('type'):
            sch['items'] = {**sch['items'], **mapped['items']}
    desc = info.get('description') or ''
    if not desc: return sch
    enum, desc = extract_enum(desc)
    if enum:
        target = sch['items'] if sch.get('type') == 'array' and isinstance(sch.get('items'), dict) and sch['items'].get('type') in (None,'string') else sch
        if target.get('type') in (None, 'string'):
            target.pop('pattern', None); target['type'] = 'string'; target['enum'] = enum
    return apply_constraints_and_desc(sch, desc)

def infer_schema(obj, fm=None, depth=0):
    fm = fm or {}
    if obj is None: return {"type": "object"}
    if isinstance(obj, dict):
        props, required = {}, []
        for k, v in obj.items():
            sch = infer_schema(v, fm, depth+1)
            sch = enrich_property(sch, v, fm_get(fm, k), name=k)
            props[k] = sch
            info = fm_get(fm, k)
            if depth == 0 and info and not info.get('optional') and k != 'id':
                required.append(k)
        out = {"type": "object", "properties": props}
        if depth == 0 and required:
            out["required"] = required
        return out
    if isinstance(obj, list):
        if not obj: return {"type": "array", "items": {}}
        merged = infer_schema(obj[0], fm, depth+1)
        for el in obj[1:]:
            merged = merge_schemas(merged, infer_schema(el, fm, depth+1))
        return {"type": "array", "items": merged}
    if isinstance(obj, bool): return {"type": "boolean"}
    if isinstance(obj, int): return {"type": "integer"}
    if isinstance(obj, float): return {"type": "number"}
    if isinstance(obj, str): return {"type": "string"}
    return {}

folder_descs = {}
def walk_folders(items, path=()):
    for item in items:
        name = item.get('name', '')
        if 'Deprecated' in name or name == 'Archive': continue
        if 'item' in item:
            folder_descs[path + (name,)] = item.get('description', '') or ''
            walk_folders(item['item'], path + (name,))
walk_folders(data.get('item', []))

def clean_folder_name(name):
    return name.replace(' API', '').replace(' Api', '').strip()

def tag_for_chain(chain):
    """Tag is always the top-level folder (subfolder endpoints inherit the parent tag)."""
    if not chain:
        return 'General'
    return clean_folder_name(chain[0])

def extract(items, chain=(), inherited=None):
    endpoints = []
    for item in items:
        name = item.get('name', '')
        if 'Deprecated' in name or name == 'Archive': continue
        if 'item' in item:
            ff = parse_field_map(item.get('description', ''))
            new_inh = dict(inherited or {}); new_inh.update(ff)
            endpoints.extend(extract(item['item'], chain + (name,), new_inh))
        elif 'request' in item:
            req = item['request']
            ef = parse_field_map(req.get('description', ''))
            fmap = dict(inherited or {}); fmap.update(ef)
            url_raw, query = req.get('url', ''), []
            if isinstance(url_raw, dict):
                query = url_raw.get('query', []) or []
                url_raw = url_raw.get('raw', '')
            endpoints.append({
                'own_fields': ef,
                'name': name, 'tag': tag_for_chain(chain), 'chain': chain,
                'method': req.get('method', 'GET').lower(), 'path': url_to_path_g(url_raw),
                'description': req.get('description', ''), 'body': req.get('body', {}) or {},
                'responses': item.get('response', []), 'field_map': fmap, 'query': query
            })
    return endpoints

endpoints = extract(data.get('item', []))

def norm_folder(name):
    # 'API Key' == 'apiKey' == 'api key' == 'Accounts API' vs 'accounts'
    return re.sub(r'[^a-z]', '', name.lower())

folder_descs_norm = {tuple(norm_folder(p) for p in k): v for k, v in folder_descs.items()}

def get_folder_desc(*names):
    return folder_descs_norm.get(tuple(norm_folder(n) for n in names), '')

instr_desc = get_folder_desc('Instruments API')
components_schemas = {
    "ErrorResponse": {"type": "object", "properties": {"code": {"type": "integer", "description": "Error code"}, "message": {"type": "string", "description": "Error message"}}}
}
components_schemas.update(build_lookup_enums(instr_desc))

instrument_refs = {
    'category': '#/components/schemas/InstrumentCategory',
    'subCategory': '#/components/schemas/InstrumentSubCategory',
    'underlyingAssets': '#/components/schemas/InstrumentUnderlyingAssets',
}

model_defs = [
    ('Instrument', ('Instruments API',), instrument_refs),
    ('InstrumentGroup', ('Instrument Groups API',), None),
    ('Calendar', ('Calendars API',), None),
    ('MarketParticipant', ('MPs API',), None),
    ('Account', ('MPs API', 'Accounts API'), None),
    ('MpApiKey', ('MPs API', 'API Key'), None),   # matches 'apiKey', 'API Key', 'Api Key' via normalization
    ('MpGroup', ('MP Groups API',), None),
    ('CircuitBreakerRule', ('CBR API',), None),
    ('TickSizeTable', ('Tick Size API',), None),
]
for comp_name, folder_key, refs in model_defs:
    desc_text = get_folder_desc(*folder_key)
    model = build_model_from_tables(parse_all_tables(desc_text), ref_overrides=refs)
    if model and model.get('properties'):
        components_schemas[comp_name] = model

if 'MpApiKey' in components_schemas:
    components_schemas['MpGroupApiKey'] = {
        "allOf": [{"$ref": "#/components/schemas/MpApiKey"}],
        "description": "API key attached to an MP Group. Structurally identical to MpApiKey, with two differences: it is scoped to an MP Group (groupId path parameter) instead of a single MP (mpId), and the set of allowed permissions is a subset of the MP API key permissions."
    }

def model_for_path(path):
    rules = [
        (r'^/api/v2/instruments(/\{id\})?$', 'Instrument'),
        (r'^/api/instrument-groups(/\{id\})?$', 'InstrumentGroup'),
        (r'^/api/v2/calendars(/\{id\})?$', 'Calendar'),
        (r'^/api/mps/\{mpId\}/api-keys(/\{apiKey\})?$', 'MpApiKey'),
        (r'^/api/mps(/\{mpId\})?$', 'MarketParticipant'),
        (r'^/api/mp-groups/\{groupId\}/api-keys(/\{apiKey\})?$', 'MpGroupApiKey'),
        (r'^/api/mp-groups(/\{groupId\})?$', 'MpGroup'),
        (r'^/api/cbrs(/\{id\})?$', 'CircuitBreakerRule'),
        (r'^/api/tick-sizes(/\{id\})?$', 'TickSizeTable'),
        (r'accounts', 'Account'),
    ]
    for pat, name in rules:
        if re.search(pat, path) and name in components_schemas:
            return name
    return None

def model_props(name):
    m = components_schemas.get(name, {})
    if 'allOf' in m:
        ref = m['allOf'][0].get('$ref','').split('/')[-1]
        return model_props(ref)
    return set(m.get('properties', {}).keys())

def substitute_model_refs(schema, mprops, ref):
    if not isinstance(schema, dict):
        return schema
    if schema.get('type') == 'object' and isinstance(schema.get('properties'), dict):
        keys = set(schema['properties'].keys())
        if keys and len(keys & mprops) >= min(5, len(mprops)) and len(keys & mprops) / len(keys) >= 0.7:
            return {"$ref": ref}
        schema['properties'] = {k: substitute_model_refs(v, mprops, ref) for k, v in schema['properties'].items()}
        return schema
    if schema.get('type') == 'array' and isinstance(schema.get('items'), dict):
        schema['items'] = substitute_model_refs(schema['items'], mprops, ref)
        return schema
    return schema

openapi = {
    "openapi": "3.0.3",
    "info": {
        "title": "Exberry Admin API",
        "version": "1.58.0",
        "description": "Exberry Admin API allows managing exchange static data (instruments, trading calendars and more) as well as sending operational commands (EOD, halt trading and more).\n\n**Sandbox environment endpoint:** `https://admin-api.uat.exberry-uat.io`\n\n**Guidelines:**\n- All numbers are stringified unless explicitly mentioned otherwise. Stringified integers are marked with pattern `^-?[0-9]+$`; stringified decimals with `format: decimal`.\n- Optional fields should be omitted from request if not required\n- System ignores any additional parameter that are sent on request body but was not specified in this document\n\n**HTTP Error Codes:**\n- 400: Maximum request size exceeded (60KB) or Invalid JSON\n- 401: Invalid token\n- 403: Authentication and authorization errors\n- 404: Route not found\n- 500: Any other error\n- 503: System not available\n- 504: Timeout",
        "contact": {"name": "Exberry Support", "url": "https://exberry.io"}
    },
    "servers": [
        {"url": "https://admin-api.uat.exberry-uat.io", "description": "Sandbox (UAT) environment"},
        {"url": "{URL_ORIGIN}", "description": "Custom environment", "variables": {"URL_ORIGIN": {"default": "https://admin-api.uat.exberry-uat.io", "description": "Base URL for the Admin API"}}}
    ],
    "components": {
        "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT", "description": "JWT token obtained from the /api/auth/token endpoint"}},
        "schemas": components_schemas,
        "responses": {
            "BadRequest": {"description": "Bad Request", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
            "Unauthorized": {"description": "Unauthorized - Invalid token", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
            "Forbidden": {"description": "Forbidden", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
            "NotFound": {"description": "Not Found", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
            "ServerError": {"description": "Internal Server Error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
        }
    },
    "security": [{"BearerAuth": []}],
    "tags": [], "paths": {}
}

def folder_intro(desc_text):
    """Folder description up to the first table — used as tag description (field tables now live in components)."""
    if not desc_text:
        return ''
    lines = []
    for line in desc_text.split('\n'):
        if line.strip().startswith('|') or line.strip().startswith('####'):
            break
        lines.append(line)
    return clean_desc('\n'.join(lines))[:1500]

# Ordered tags with descriptions (one tag per top-level folder)
tag_order, tag_desc = [], {}
for ep in endpoints:
    t = ep['tag']
    if t not in tag_order:
        tag_order.append(t)
        top_chain = (ep['chain'][0],) if ep['chain'] else ()
        tag_desc[t] = folder_intro(folder_descs.get(top_chain, ''))

openapi["tags"] = [
    ({"name": t, "description": tag_desc[t]} if tag_desc.get(t) else {"name": t})
    for t in tag_order
]

def strip_field_tables(text):
    """Remove Field/Parameter markdown tables from operation descriptions (fields now live in components).
    Error-code tables and other reference tables are kept."""
    if not text: return text
    lines = text.split('\n')
    out, skip = [], False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('|') and i + 1 < len(lines) and is_separator(lines[i+1]):
            first = stripped.strip('|').split('|')[0].strip().lower()
            skip = first in ('field', 'parameter', 'name')
            if skip: continue
        elif not stripped.startswith('|'):
            skip = False
        if not skip:
            out.append(line)
    res = '\n'.join(out)
    # drop headings left orphaned by table removal (heading directly followed by another heading or end)
    prev = None
    while prev != res:
        prev = res
        res = re.sub(r'#{2,6}[^\n]*\n+(?=#{2,6}|\Z)', '', res)
    res = re.sub(r'\n{3,}', '\n\n', res)
    return res.strip()

def truncate_arrays(obj, max_items=2):
    """Keep examples representative but short: cap all arrays at max_items."""
    if isinstance(obj, dict):
        return {k: truncate_arrays(v, max_items) for k, v in obj.items()}
    if isinstance(obj, list):
        return [truncate_arrays(v, max_items) for v in obj[:max_items]]
    return obj

used_op_ids = set()
for ep in endpoints:
    path, method = ep['path'], ep['method']
    if not path: continue
    openapi["paths"].setdefault(path, {})
    if method in openapi["paths"][path]: continue
    fm = ep['field_map']
    model = model_for_path(path)
    mref = f"#/components/schemas/{model}" if model else None
    mprops = model_props(model) if model else set()

    params = []
    for p in re.findall(r'\{([^}]+)\}', path):
        pdesc = fm.get(p, {}).get('description') or f"The {p} identifier"
        params.append({"name": p, "in": "path", "required": True, "schema": {"type": "string"}, "description": pdesc})
    for q in ep['query']:
        key = q.get('key')
        if not key: continue
        qdesc = clean_desc(q.get('description') or '') or fm.get(key, {}).get('description', '')
        qschema = {"type": "string"}
        info = fm.get(key)
        if info:
            mapped = openapi_type(info['type'])
            if mapped and mapped.get('type') != 'array': qschema = mapped
        param = {"name": key, "in": "query", "required": False, "schema": qschema}
        if qdesc: param["description"] = qdesc
        if q.get('value'): param["example"] = q.get('value')
        params.append(param)

    # GET endpoints documenting filters via a field table (e.g. Get Instruments): promote to query parameters
    if method == 'get' and not ep['query'] and ep.get('own_fields'):
        for fname, info in ep['own_fields'].items():
            if info.get('nested'): continue
            qschema = openapi_type(info['type']) or {"type": "string"}
            qdesc = info.get('description') or ''
            enum, qdesc = extract_enum(qdesc)
            if enum:
                target = qschema['items'] if qschema.get('type') == 'array' and qschema.get('items', {}).get('type') in (None, 'string') else qschema
                if target.get('type') in (None, 'string'):
                    target.pop('pattern', None); target['type'] = 'string'; target['enum'] = enum
            param = {"name": fname, "in": "query", "required": False, "schema": qschema}
            if qdesc: param["description"] = qdesc
            params.append(param)

    request_body = None
    is_write = method in ('post', 'put', 'patch')
    if ep['body'].get('mode') == 'raw' and ep['body'].get('raw'):
        bj = safe_json(ep['body']['raw'])
        if bj is not None:
            if is_write and model:
                request_body = {"required": True, "content": {"application/json": {
                    "schema": {"$ref": mref}, "example": bj}}}
            else:
                schema = infer_schema(bj, fm)
                request_body = {"required": True, "content": {"application/json": {"schema": schema, "example": bj}}}

    responses = {"200": {"description": "Successful response", "content": {"application/json": {"schema": {"type": "object"}}}}}
    for resp in ep['responses']:
        code = str(resp.get('code', 200))
        rb = safe_json(resp.get('body', ''))
        robj = {"description": resp.get('name', resp.get('status', 'Response'))}
        if rb is not None:
            rschema = infer_schema(rb, fm, depth=1)
            if model and code == '200':
                rschema = substitute_model_refs(rschema, mprops, mref)
            robj["content"] = {"application/json": {"schema": rschema, "example": truncate_arrays(rb)}}
        responses[code] = robj
    for c, rname in [("400","BadRequest"),("401","Unauthorized"),("403","Forbidden"),("404","NotFound"),("500","ServerError")]:
        if c not in responses:
            responses[c] = {"$ref": f"#/components/responses/{rname}"}

    op_id = re.sub(r'_+', '_', re.sub(r'[^a-zA-Z0-9]', '_', ep['name'])).strip('_')
    if op_id in used_op_ids:
        op_id = f"{re.sub(r'[^a-zA-Z0-9]', '_', ep['tag'])}_{op_id}"
    used_op_ids.add(op_id)

    operation = {
        "operationId": op_id, "summary": ep['name'], "tags": [ep['tag']],
        "description": strip_field_tables(ep['description']), "parameters": params, "responses": responses
    }
    if path == '/api/auth/token': operation["security"] = []
    if request_body: operation["requestBody"] = request_body
    openapi["paths"][path][method] = operation

used_tags = set()
for _p, _methods in openapi["paths"].items():
    for _m, _op in _methods.items():
        used_tags.update(_op.get('tags', []))
openapi["tags"] = [t for t in openapi["tags"] if t["name"] in used_tags]

# --- Optional overrides: spec_overrides.json next to the generator ---
import os
ov_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'spec_overrides.json')
if os.path.exists(ov_path):
    ov = json.load(open(ov_path, encoding='utf-8'))
    if 'info' in ov:
        openapi['info'].update(ov['info'])
    for tname, tdesc in (ov.get('tags') or {}).items():
        for t in openapi['tags']:
            if t['name'] == tname: t['description'] = tdesc
    for opid, fields in (ov.get('operations') or {}).items():
        for p, methods in openapi['paths'].items():
            for m, op in methods.items():
                if isinstance(op, dict) and op.get('operationId') == opid:
                    op.update(fields)
    for dotted, text in (ov.get('schema_descriptions') or {}).items():
        node = openapi['components']['schemas']
        parts = dotted.split('.')
        try:
            for part in parts:
                node = node[part]
            node['description'] = text
        except (KeyError, TypeError):
            print(f"WARNING: override path not found: {dotted}")

# sort components alphabetically for stable diffs and easy lookup
openapi['components']['schemas'] = dict(sorted(openapi['components']['schemas'].items()))

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(openapi, f, indent=2, ensure_ascii=False)
print(f"written {OUT}")
