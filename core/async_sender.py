import asyncio
import time
import json
from dataclasses import dataclass
from typing import List, Optional, Callable
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
from core.sender import BotResponse

class TokenBucketRateLimiter:

    def __init__(self, rate: float=10.0, burst: int=0):
        self.rate = rate
        self.burst = burst if burst else max(1, int(rate))
        self.tokens = float(self.burst)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
                self.last_refill = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            await asyncio.sleep(1.0 / self.rate)

class AsyncSender:

    def __init__(self, url: str, method: str='POST', data_field: str='message', response_field: str='response', content_type: str='json', timeout: int=30, headers: Optional[dict]=None, rate_limit: float=10.0, transport: str='rest', body_data: Optional[dict]=None):
        if not HAS_AIOHTTP:
            raise ImportError('aiohttp is required for concurrent scanning. Install it with: pip install aiohttp>=3.9.0')
        self.url = url
        self.method = method.upper()
        self.data_field = data_field
        self.response_field = response_field
        self.content_type = content_type
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.transport = transport
        self.body_data = body_data
        self.rate_limiter = TokenBucketRateLimiter(rate=rate_limit)
        self.headers = {'User-Agent': 'LLM-RedTeam-Scanner/1.0'}
        if headers:
            self.headers.update(headers)
        self._common_fields = ['response', 'reply', 'message', 'text', 'answer', 'output', 'content', 'result', 'data', 'bot_response', 'bot_reply', 'assistant', 'completion', 'generated_text']

    async def send_batch(self, payloads: List[dict], concurrency: int=5, on_result: Optional[Callable]=None) -> List[BotResponse]:
        results = [None] * len(payloads)
        semaphore = asyncio.Semaphore(concurrency)
        async with aiohttp.ClientSession(headers=self.headers, timeout=self.timeout) as session:
            tasks = []
            for (i, payload) in enumerate(payloads):
                task = asyncio.create_task(self._send_one(session, semaphore, i, payload, results, on_result))
                tasks.append(task)
            await asyncio.gather(*tasks, return_exceptions=True)
        for i in range(len(results)):
            if results[i] is None:
                results[i] = BotResponse(status_code=0, raw_body='', reply_text='', headers={}, elapsed_ms=0, error='Task failed or was cancelled', success=False)
        return results

    async def _send_one(self, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, index: int, payload: dict, results: list, on_result: Optional[Callable]):
        async with semaphore:
            await self.rate_limiter.acquire()
            message = payload['payload']
            start = time.monotonic()
            try:
                if self.body_data:
                    import copy
                    payload_body = copy.deepcopy(self.body_data)
                    payload_body[self.data_field] = message
                else:
                    payload_body = {self.data_field: message}

                if self.content_type == 'json':
                    kwargs = {'json': payload_body}
                else:
                    kwargs = {'data': payload_body}
                if self.transport == 'sse':
                    result = await self._send_sse(session, kwargs, start)
                else:
                    result = await self._send_rest(session, kwargs, start)
                results[index] = result
            except asyncio.TimeoutError:
                results[index] = BotResponse(status_code=0, raw_body='', reply_text='', headers={}, elapsed_ms=0, error='Request timed out', success=False)
            except aiohttp.ClientError as e:
                results[index] = BotResponse(status_code=0, raw_body='', reply_text='', headers={}, elapsed_ms=0, error=str(e), success=False)
            except Exception as e:
                results[index] = BotResponse(status_code=0, raw_body='', reply_text='', headers={}, elapsed_ms=0, error=f'Unexpected: {e}', success=False)
            if on_result and results[index]:
                on_result(index, results[index])

    async def _send_rest(self, session, kwargs, start) -> BotResponse:
        async with session.request(self.method, self.url, **kwargs) as resp:
            elapsed = (time.monotonic() - start) * 1000
            body = await resp.text()
            reply_text = self._extract_reply(body)
            return BotResponse(status_code=resp.status, raw_body=body[:5000], reply_text=reply_text, headers=dict(resp.headers), elapsed_ms=round(elapsed, 2), success=True)

    async def _send_sse(self, session, kwargs, start) -> BotResponse:
        kwargs['headers'] = {'Accept': 'text/event-stream'}
        chunks = []
        async with session.request(self.method, self.url, **kwargs) as resp:
            async for line in resp.content:
                decoded = line.decode('utf-8', errors='replace').strip()
                if decoded.startswith('data:'):
                    data_part = decoded[5:].strip()
                    if data_part == '[DONE]':
                        break
                    try:
                        obj = json.loads(data_part)
                        for choice in obj.get('choices', []):
                            delta = choice.get('delta', {})
                            if 'content' in delta:
                                chunks.append(delta['content'])
                    except (json.JSONDecodeError, TypeError):
                        chunks.append(data_part)
            elapsed = (time.monotonic() - start) * 1000
            full_text = ''.join(chunks)
            if not full_text:
                body = await resp.text()
                full_text = self._extract_reply(body)
            return BotResponse(status_code=resp.status, raw_body=full_text[:5000], reply_text=full_text, headers=dict(resp.headers), elapsed_ms=round(elapsed, 2), success=True)

    def _extract_reply(self, body_text: str) -> str:
        try:
            data = json.loads(body_text)
        except (ValueError, TypeError):
            return body_text[:3000]
        if isinstance(data, dict):
            if self.response_field in data:
                val = data[self.response_field]
                return str(val) if not isinstance(val, str) else val
            for key in self._common_fields:
                if key in data:
                    val = data[key]
                    if isinstance(val, str):
                        return val
                    elif isinstance(val, dict):
                        for inner in ['content', 'text', 'message']:
                            if inner in val:
                                return str(val[inner])
                    elif isinstance(val, list) and val:
                        first = val[0]
                        if isinstance(first, str):
                            return first
                        elif isinstance(first, dict):
                            for inner in ['content', 'text', 'message']:
                                if inner in first:
                                    return str(first[inner])
            if 'choices' in data and isinstance(data['choices'], list):
                for choice in data['choices']:
                    if isinstance(choice, dict):
                        msg = choice.get('message', choice.get('delta', {}))
                        if isinstance(msg, dict) and 'content' in msg:
                            return str(msg['content'])
            return str(data)[:3000]
        return body_text[:3000]