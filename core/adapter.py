import re
import random
from typing import List
from core.recon import ReconProfile


class PayloadAdapter:
    STRATEGIES = ['prepend_context', 'sandwich', 'progressive', 'continuation', 'error_context']

    def __init__(self, profile: ReconProfile, evasion_enabled: bool = False):
        self.profile = profile
        self.evasion_enabled = evasion_enabled
        self._evasion_engine = None
        if evasion_enabled:
            from core.evasion import EvasionEngine
            self._evasion_engine = EvasionEngine()

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def adapt(self, payloads: List[dict]) -> List[dict]:
        context_phrases = self.profile.context_phrases or ['Can you help me?', 'I have a question.']
        keywords = self.profile.keywords[:10] if self.profile.keywords else ['service']
        domain = self.profile.domain
        adapted = []

        for p in payloads:
            original = p['payload']
            # Humanize the raw injection text before embedding it
            humanized = self._humanize(original)

            strategy = random.choice(self.STRATEGIES)
            ctx = random.choice(context_phrases)

            if strategy == 'prepend_context':
                new_payload = self._prepend(ctx, humanized)
            elif strategy == 'sandwich':
                ctx2 = random.choice(context_phrases)
                new_payload = self._sandwich(ctx, humanized, ctx2)
            elif strategy == 'progressive':
                new_payload = self._progressive(ctx, humanized, keywords)
            elif strategy == 'continuation':
                new_payload = self._continuation(ctx, humanized)
            elif strategy == 'error_context':
                new_payload = self._error_context(humanized, domain, keywords)
            else:
                new_payload = humanized

            adapted.append({
                'id': p['id'],
                'family': p.get('family', 'unknown'),
                'original': original,
                'payload': new_payload,
                'strategy': strategy,
            })

        if self.evasion_enabled and self._evasion_engine:
            adapted = self._evasion_engine.apply(adapted, evasion_ratio=0.3)

        return adapted

    # ──────────────────────────────────────────────────────────────────────────
    # Payload humanisation
    # ──────────────────────────────────────────────────────────────────────────

    def _humanize(self, text: str) -> str:
        """
        Strip only the structural markup wrappers from a raw injection payload
        so it reads as clean prose when embedded inside a conversational context.

        Rules:
          - HTML comment wrapper <!-- … -->  →  inner text only
          - XML / HTML element wrappers <tag>…</tag>  →  inner text only
          - Triple-backtick code fences ```lang\n…\n```  →  inner text only
          - Simple single-key JSON object {"key": "value"}  →  value only
          - BEGIN … END delimiters  →  inner text only
          - [[ … ]] brackets  →  inner text only

        Everything else — casing, spacing, punctuation, encoding tricks — is
        preserved exactly as written in the original payload.
        """
        t = text.strip()

        # HTML comments: <!-- content --> → content
        t = re.sub(r'<!--\s*(.*?)\s*-->', r'\1', t, flags=re.DOTALL)

        # XML / HTML element wrappers: <tag …>content</tag> → content
        # Applied repeatedly to handle nested tags
        for _ in range(3):
            t = re.sub(r'<[a-zA-Z][^>]*>(.*?)</[a-zA-Z][^>]*>', r'\1', t, flags=re.DOTALL)

        # Triple-backtick code fences: ```lang\ncontent\n``` → content
        t = re.sub(r'```[a-zA-Z]*[ \t]*\n?(.*?)\n?```', r'\1', t, flags=re.DOTALL)

        # Single-key JSON object wrapper: {"key": "value"} → value
        json_match = re.match(r'^\s*\{\s*"[^"]+"\s*:\s*"(.+?)"\s*\}\s*$', t, re.DOTALL)
        if json_match:
            t = json_match.group(1)

        # BEGIN / END block delimiters
        t = re.sub(r'^BEGIN[ \t]*\n', '', t.strip(), flags=re.IGNORECASE)
        t = re.sub(r'\nEND[ \t]*$', '', t.strip(), flags=re.IGNORECASE)

        # [[ … ]] bracket wrapper
        bracket_match = re.match(r'^\[\[(.+?)\]\]$', t.strip(), re.DOTALL)
        if bracket_match:
            t = bracket_match.group(1)

        # Collapse 3+ newlines to a single blank line, trim leading/trailing space
        t = re.sub(r'\n{3,}', '\n\n', t)
        return t.strip()

    # ──────────────────────────────────────────────────────────────────────────
    # Composition strategies
    # ──────────────────────────────────────────────────────────────────────────

    def _prepend(self, context: str, injection: str) -> str:
        connectors = [
            'Also, ', 'By the way, ', 'One more thing: ',
            'Additionally, ', 'Quick question: ', 'Oh, and also — ',
        ]
        connector = random.choice(connectors)
        # Ensure there is always exactly one space between context and connector
        return f'{context} {connector}{injection}'

    def _sandwich(self, before: str, injection: str, after: str) -> str:
        transitions = [
            'On a related note, I also wanted to ask: ',
            'While we are at it, ',
            'I also have a follow-up question: ',
            '',
        ]
        transition = random.choice(transitions)
        return f'{before}\n\n{transition}{injection}\n\n{after}'

    def _progressive(self, context: str, injection: str, keywords: List[str]) -> str:
        kw = random.choice(keywords) if keywords else 'this topic'
        transitions = [
            f'I was reading about {kw} and came across something I wanted to ask you about. ',
            f'While looking into {kw}, I found something a bit confusing. ',
            f'Speaking of {kw}, I had another thought: ',
            f'Thanks for the info about {kw}. On a different note, ',
        ]
        transition = random.choice(transitions)
        return f'{context}\n{transition}{injection}'

    def _continuation(self, context: str, injection: str) -> str:
        continuations = [
            'Thanks for that! Actually, I also wanted to ask — ',
            'Great, that helps. One more question: ',
            'Perfect. While I have you, I also wanted to know: ',
            'I appreciate that. Could you also help me with this: ',
            'Got it. One more thing before I go: ',
        ]
        cont = random.choice(continuations)
        return f'{context}\n\n{cont}{injection}'

    def _error_context(self, injection: str, domain: str, keywords: List[str]) -> str:
        kw = random.choice(keywords) if keywords else 'the service'
        error_frames = [
            f"I am having a problem with {kw} and I am not sure what to make of this message: {injection}",
            f'Something seems off with {kw}. When I checked, I noticed the following: {injection}',
            f'I keep seeing this when I try to use {kw} — can you help me understand it? {injection}',
            f'The system showed me this message related to {kw}. What does it mean? {injection}',
        ]
        return random.choice(error_frames)