import json
import random
from typing import List, Optional
from pathlib import Path

def load_payloads(corpus_path: str, max_count: int=200, families: Optional[List[str]]=None) -> List[dict]:
    path = Path(corpus_path)
    if not path.exists():
        print(f'   Corpus not found: {corpus_path}')
        return []
    print(f'  📂 Loading corpus: {path.name}...', end=' ')
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    all_payloads = data.get('payloads', [])
    total = len(all_payloads)
    if families:
        all_payloads = [p for p in all_payloads if p.get('family') in families]
    print(f'({total} total, {len(all_payloads)} after family filter)')
    if len(all_payloads) <= max_count:
        return all_payloads
    return _stratified_sample(all_payloads, max_count)

def _stratified_sample(payloads: List[dict], max_count: int) -> List[dict]:
    families = {}
    for p in payloads:
        fam = p.get('family', 'unknown')
        families.setdefault(fam, []).append(p)
    num_families = len(families)
    if num_families == 0:
        return []
    base_per_family = max(1, max_count // num_families)
    sampled = []
    for (fam, items) in families.items():
        count = min(base_per_family, len(items))
        sampled.extend(random.sample(items, count))
    remaining = max_count - len(sampled)
    if remaining > 0:
        already_ids = {p['id'] for p in sampled}
        pool = [p for p in payloads if p['id'] not in already_ids]
        if pool:
            extra = random.sample(pool, min(remaining, len(pool)))
            sampled.extend(extra)
    random.shuffle(sampled)
    return sampled[:max_count]

def get_families(corpus_path: str) -> List[str]:
    path = Path(corpus_path)
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return sorted(set((p.get('family', 'unknown') for p in data.get('payloads', []))))