import os
import time
import sys
import asyncio
from pathlib import Path
from typing import Optional
from core.recon import Recon
from core.sender import Sender
from core.payload_loader import load_payloads
from core.adapter import PayloadAdapter
from core.analyzer import Analyzer, Finding, CONFIRMED, LIKELY, POSSIBLE, SAFE
from core.reporter import Reporter
BANNER = '\n  ██▓     ██▓     ███▄ ▄███▓      ██▀███  ▓█████ ▓█████▄ ▄▄▄█████▓▓█████ ▄▄▄       ███▄ ▄███▓\n ▓██▒    ▓██▒    ▓██▒▀█▀ ██▒     ▓██ ▒ ██▒▓█   ▀ ▒██▀ ██▌▓  ██▒ ▓▒▓█   ▀▒████▄    ▓██▒▀█▀ ██▒\n ▒██░    ▒██░    ▓██    ▓██░     ▓██ ░▄█ ▒▒███   ░██   █▌▒ ▓██░ ▒░▒███  ▒██  ▀█▄  ▓██    ▓██░\n ▒██░    ▒██░    ▒██    ▒██      ▒██▀▀█▄  ▒▓█  ▄ ░▓█▄   ▌░ ▓██▓ ░ ▒▓█  ▄░██▄▄▄▄██ ▒██    ▒██ \n ░██████▒░██████▒▒██▒   ░██▒     ░██▓ ▒██▒░▒████▒░▒████▓   ▒██▒ ░ ░▒████▒▓█   ▓██▒▒██▒   ░██▒\n ░ ▒░▓  ░░ ▒░▓  ░░ ▒░   ░  ░     ░ ▒▓ ░▒▓░░░ ▒░ ░ ▒▒▓  ▒   ▒ ░░   ░░ ▒░ ░▒▒   ▓▒█░░ ▒░   ░  ░\n ░ ░ ▒  ░░ ░ ▒  ░░  ░      ░       ░▒ ░ ▒░ ░ ░  ░ ░ ▒  ▒     ░     ░ ░  ░ ░   ▒▒ ░░  ░      ░\n   ░ ░     ░ ░   ░      ░          ░░   ░    ░    ░ ░  ░   ░         ░    ░   ▒   ░      ░   \n     ░  ░    ░  ░       ░           ░        ░  ░   ░                 ░  ░     ░  ░       ░   \n                                                  ░                                          \n                      ╔══════════════════════════════════════╗\n                      ║  LLM RED TEAM SCANNER v1.0           ║\n                      ║  Adaptive Prompt Injection Testing   ║\n                      ║  Made by : Ishaani                   ║\n                      ║  [ github.com/mindxflayer ]          ║\n                      ╚══════════════════════════════════════╝\n'

class Scanner:

    def __init__(self, url: str, method: str='POST', data_field: str='message', response_field: str='response', content_type: str='json', max_payloads: int=200, delay: float=0.5, timeout: int=30, headers: Optional[dict]=None, output_dir: str='./reports', verbose: bool=False, concurrency: int=1, rate_limit: float=10.0, transport: str='rest', ws_send_field: str='message', ws_recv_field: str='response', evasion: bool=False, multi_turn: bool=False, multi_turn_chains: Optional[list]=None, fuzz: bool=False, fuzz_generations: int=3, fuzz_population: int=10, judge_url: Optional[str]=None, judge_model: str='gpt-4o-mini', judge_api_key: Optional[str]=None, body_data: Optional[dict]=None):
        self.url = url
        self.max_payloads = max_payloads
        self.output_dir = output_dir
        self.verbose = verbose
        self.concurrency = concurrency
        self.rate_limit = rate_limit
        self.evasion = evasion
        self.multi_turn = multi_turn
        self.multi_turn_chains = multi_turn_chains
        self.fuzz = fuzz
        self.fuzz_generations = fuzz_generations
        self.fuzz_population = fuzz_population
        self.judge_url = judge_url
        self.judge_model = judge_model
        self.judge_api_key = judge_api_key
        self.transport = transport
        self.body_data = body_data
        self.sender = Sender(url=url, method=method, data_field=data_field, response_field=response_field, content_type=content_type, timeout=timeout, headers=headers, delay=delay, transport=transport, ws_send_field=ws_send_field, ws_recv_field=ws_recv_field, body_data=body_data)
        self.async_sender = None
        if concurrency > 1:
            try:
                from core.async_sender import AsyncSender
                self.async_sender = AsyncSender(url=url, method=method, data_field=data_field, response_field=response_field, content_type=content_type, timeout=timeout, headers=headers, rate_limit=rate_limit, transport=transport, body_data=body_data)
            except ImportError:
                print('   aiohttp not found — falling back to sequential mode')
                self.concurrency = 1
        self.llm_judge = None
        if judge_url:
            try:
                from core.llm_judge import LLMJudge
                self.llm_judge = LLMJudge(judge_url=judge_url, judge_model=judge_model, api_key=judge_api_key)
                if self.llm_judge.is_available():
                    print(f'    LLM Judge: {judge_model} @ {judge_url}')
                else:
                    print(f'   LLM Judge unreachable at {judge_url} — skipping')
                    self.llm_judge = None
            except Exception as e:
                print(f'   LLM Judge init failed: {e}')
                self.llm_judge = None
        base_dir = Path(__file__).parent.parent
        self.corpus_attack = str(base_dir / 'ids_prompt_injection_corpus_vast.json')
        self.corpus_defensive = str(base_dir / 'defensive_prompt_corpus_60000.json')

    def run(self):

        print(f'   Target: {self.url}')
        print(f'    Method: {self.sender.method} | Data field: {self.sender.data_field}')
        print(f'   Max payloads: {self.max_payloads} per corpus')
        print(f'    Delay: {self.sender.delay}s | Timeout: {self.sender.timeout}s')
        features = []
        if self.concurrency > 1:
            features.append(f'Async×{self.concurrency}')
        if self.transport != 'rest':
            features.append(f'{self.transport.upper()}')
        if self.evasion:
            features.append('Evasion')
        if self.multi_turn:
            features.append('Multi-Turn')
        if self.fuzz:
            features.append(f'Fuzz×{self.fuzz_generations}')
        if self.llm_judge:
            features.append('Judge')
        if features:
            print(f"   Features: {' | '.join(features)}")
        print()
        start_time = time.time()
        recon = Recon(self.sender, verbose=self.verbose)
        profile = recon.execute()
        print('\n PHASE 2: PAYLOAD LOADING & ADAPTATION')
        print('─' * 60)
        attack_payloads = load_payloads(self.corpus_attack, self.max_payloads)
        defensive_payloads = load_payloads(self.corpus_defensive, self.max_payloads)
        all_raw = attack_payloads + defensive_payloads
        print(f'   Total payloads sampled: {len(all_raw)}')
        adapter = PayloadAdapter(profile, evasion_enabled=self.evasion)
        adapted = adapter.adapt(all_raw)
        evasion_count = sum((1 for p in adapted if p.get('evasion')))
        print(f'   Adapted {len(adapted)} payloads with chatbot context')
        if evasion_count:
            print(f'    Applied WAF evasion to {evasion_count} payloads')
        print()
        print(' PHASE 3: PAYLOAD DELIVERY')
        print('─' * 60)
        analyzer = Analyzer(profile, llm_judge=self.llm_judge)
        findings = []
        severity_counts = {CONFIRMED: 0, LIKELY: 0, POSSIBLE: 0, SAFE: 0}
        if self.concurrency > 1 and self.async_sender:
            (findings, severity_counts) = self._spray_async(adapted, analyzer)
        else:
            (findings, severity_counts) = self._spray_sequential(adapted, analyzer)
        print()
        if self.multi_turn:
            mt_findings = self._run_multi_turn(adapted, analyzer, profile)
            for f in mt_findings:
                findings.append(f)
                severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
        if self.fuzz:
            fuzz_findings = self._run_fuzzing(findings, analyzer)
            for f in fuzz_findings:
                findings.append(f)
                severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
        elapsed = time.time() - start_time
        print(f'\n PHASE 4: REPORT GENERATION')
        print('─' * 60)
        reporter = Reporter(self.output_dir)
        html_path = reporter.generate(findings, profile, self.url, elapsed)
        print(f"\n{'' * 60}")
        print(f'  SCAN COMPLETE')
        print(f'  Duration : {elapsed:.1f}s')
        print(f'  Total    : {len(findings)} payloads tested')
        print(f'  ─────────────────────────────')
        print(f'   CONFIRMED : {severity_counts[CONFIRMED]}')
        print(f'   LIKELY    : {severity_counts[LIKELY]}')
        print(f'   POSSIBLE  : {severity_counts[POSSIBLE]}')
        print(f'   SAFE      : {severity_counts[SAFE]}')
        print(f'  ─────────────────────────────')
        print(f'  Report: {html_path}')
        print(f"{'' * 60}\n")
        return findings

    def _spray_sequential(self, adapted, analyzer):
        findings = []
        severity_counts = {CONFIRMED: 0, LIKELY: 0, POSSIBLE: 0, SAFE: 0}
        total = len(adapted)
        for (i, payload) in enumerate(adapted, 1):
            pct = i / total * 100
            bar_len = 30
            filled = int(bar_len * i / total)
            bar = '█' * filled + '░' * (bar_len - filled)
            result = self.sender.send(payload['payload'])
            if result.success:
                finding = analyzer.analyse(payload, result.reply_text, result.elapsed_ms)
            else:
                finding = Finding(payload_id=payload['id'], family=payload['family'], strategy=payload.get('strategy', 'raw'), original_payload=payload.get('original', payload['payload']), adapted_payload=payload['payload'], response=f'ERROR: {result.error}', severity=SAFE, score=0.0, signals=[f'Request failed: {result.error}'], elapsed_ms=0)
            findings.append(finding)
            severity_counts[finding.severity] += 1
            status = f'\r  [{bar}] {pct:5.1f}% ({i}/{total}) | {severity_counts[CONFIRMED]} {severity_counts[LIKELY]} {severity_counts[POSSIBLE]} {severity_counts[SAFE]}'
            sys.stdout.write(status)
            sys.stdout.flush()
            self.sender.wait()
        return (findings, severity_counts)

    def _spray_async(self, adapted, analyzer):
        findings = []
        severity_counts = {CONFIRMED: 0, LIKELY: 0, POSSIBLE: 0, SAFE: 0}
        total = len(adapted)
        completed = [0]

        def on_result(index, bot_response):
            completed[0] += 1
            pct = completed[0] / total * 100
            bar_len = 30
            filled = int(bar_len * completed[0] / total)
            bar = '█' * filled + '░' * (bar_len - filled)
            status = f'\r  [{bar}] {pct:5.1f}% ({completed[0]}/{total})'
            sys.stdout.write(status)
            sys.stdout.flush()
        print(f'   Sending {total} payloads with concurrency={self.concurrency}')
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(self.async_sender.send_batch(adapted, concurrency=self.concurrency, on_result=on_result))
        finally:
            loop.close()
        for (i, (payload, result)) in enumerate(zip(adapted, results)):
            if result.success:
                finding = analyzer.analyse(payload, result.reply_text, result.elapsed_ms)
            else:
                finding = Finding(payload_id=payload['id'], family=payload['family'], strategy=payload.get('strategy', 'raw'), original_payload=payload.get('original', payload['payload']), adapted_payload=payload['payload'], response=f'ERROR: {result.error}', severity=SAFE, score=0.0, signals=[f'Request failed: {result.error}'], elapsed_ms=0)
            findings.append(finding)
            severity_counts[finding.severity] += 1
        sys.stdout.write(f"\r  [{'█' * 30}] 100.0% ({total}/{total}) | {severity_counts[CONFIRMED]} {severity_counts[LIKELY]} {severity_counts[POSSIBLE]} {severity_counts[SAFE]}")
        sys.stdout.flush()
        return (findings, severity_counts)

    def _run_multi_turn(self, adapted, analyzer, profile):
        print(f'\n\n PHASE 3b: MULTI-TURN ATTACKS')
        print('─' * 60)
        from core.multi_turn import MultiTurnAttack
        high_value = [p for p in adapted if p.get('family') in {'direct_override', 'roleplay', 'authority', 'persona_manipulation', 'system_prompt_extraction', 'instruction_override'}]
        if not high_value:
            high_value = adapted[:20]
        mt = MultiTurnAttack(sender=self.sender, analyzer=analyzer, profile=profile, verbose=self.verbose)
        chains = self.multi_turn_chains
        max_chains = min(20, len(high_value))
        print(f'   Running up to {max_chains} multi-turn chains...')
        mt_findings = mt.execute(high_value, chains=chains, max_chains=max_chains)
        confirmed = sum((1 for f in mt_findings if f.severity == CONFIRMED))
        likely = sum((1 for f in mt_findings if f.severity == LIKELY))
        print(f'   Multi-turn results: {len(mt_findings)} tested, {confirmed} {likely}')
        return mt_findings

    def _run_fuzzing(self, findings, analyzer):
        print(f'\n\n PHASE 3c: GENETIC PAYLOAD FUZZING')
        print('─' * 60)
        from core.fuzzer import GeneticFuzzer
        seeds = [f for f in findings if f.severity in (CONFIRMED, LIKELY)]
        if not seeds:
            seeds = [f for f in findings if f.severity == POSSIBLE][:5]
        if not seeds:
            print('   No high-scoring payloads found — skipping fuzzing')
            return []
        print(f'   Seeds: {len(seeds)} high-scoring payloads')
        print(f'   Generations: {self.fuzz_generations} | Population: {self.fuzz_population}')
        fuzzer = GeneticFuzzer(sender=self.sender, analyzer=analyzer, population_size=self.fuzz_population, generations=self.fuzz_generations, verbose=self.verbose)
        fuzz_findings = fuzzer.evolve(seeds)
        confirmed = sum((1 for f in fuzz_findings if f.severity == CONFIRMED))
        likely = sum((1 for f in fuzz_findings if f.severity == LIKELY))
        print(f'\n   Fuzzing results: {len(fuzz_findings)} variants tested, {confirmed} {likely}')
        return fuzz_findings