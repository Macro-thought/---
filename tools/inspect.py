import json
import collections

g = json.load(open('data/graph_v1.json', encoding='utf-8'))
nodes = {e['id']: e for e in g['entities']}
airports = {e['id']: e for e in g['entities'] if e['type'] == '机场'}

print('Q51756 outgoing rels:', collections.Counter(e['rel'] for e in g['edges'] if e['h'] == 'Q51756'))
print('Q5099568 outgoing rels:', collections.Counter(e['rel'] for e in g['edges'] if e['h'] == 'Q5099568'))

aff = collections.defaultdict(set)
sub = collections.defaultdict(set)
for e in g['edges']:
    if e['rel'] == '枢纽机场' and airports.get(e['t'], {}).get('props', {}).get('airport_class') == '普通机场':
        a = nodes[e['h']]
        aff[a['props'].get('country')].add(e['h'])
        sub[a['props'].get('p31_subtype')].add(e['h'])
print('affected by country:', {k: len(v) for k, v in aff.items()})
print('affected by subtype:', {k: len(v) for k, v in sub.items()})

normal = collections.Counter(
    e['t'] for e in g['edges']
    if e['rel'] == '枢纽机场' and airports.get(e['t'], {}).get('props', {}).get('airport_class') == '普通机场')
print('normal hub airports used:', len(normal), normal.most_common(10))

hub_air = {e['h'] for e in g['edges'] if e['rel'] == '枢纽机场'}
print('airlines with hub', len(hub_air))

for rel in ['枢纽机场', '运营机型', '国家', '总部', '母组织', '子公司', '航空联盟', '所有者']:
    has = {e['h'] for e in g['edges'] if e['rel'] == rel}
    print(rel, len(has))

# per-country airline counts and hub counts
for c in ['Q148', 'Q17', 'Q865', 'Q884']:
    airlines = [n for n in g['entities'] if n['type'] == '航空公司' and n['props'].get('country') == c]
    print('country', c, 'airlines', len(airlines))
