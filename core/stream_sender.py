import json
import time
import requests
from typing import Optional
from core.sender import BotResponse
try:
    import websockets
    import asyncio
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

class SSESender:

    def __init__(self, url: str, method: str='POST', data_field: str='message', response_field: str='response', content_type: str='json', timeout: int=60, headers: Optional[dict]=None, delay: float=0.5, body_data: Optional[dict]=None):
        import requests
        self.url = url
        self.method = method.upper()
        self.data_field = data_field
        self.response_field = response_field
        self.content_type = content_type
        self.timeout = timeout
        self.delay = delay
        self.body_data = body_data
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'LLM-RedTeam-Scanner/1.0'})
        if headers:
            self.session.headers.update(headers)

    def send(self, message: str, retries: int=2) -> BotResponse:
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
        kwargs['timeout'] = self.timeout
        kwargs['stream'] = True
        kwargs['headers'] = {'Accept': 'text/event-stream'}
        last_error = None
        for attempt in range(retries + 1):
            try:
                start = time.time()
                resp = self.session.request(self.method, self.url, **kwargs)
                chunks = []
                ct = resp.headers.get('content-type', '')
                if 'text/event-stream' in ct or 'stream' in ct:
                    for line in resp.iter_lines(decode_unicode=True):
                        if line is None:
                            continue
                        line = line.strip()
                        if line.startswith('data:'):
                            data_part = line[5:].strip()
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
                    full_text = ''.join(chunks)
                else:
                    full_text = self._extract_reply_from_json(resp.text)
                elapsed = (time.time() - start) * 1000
                return BotResponse(status_code=resp.status_code, raw_body=full_text[:5000], reply_text=full_text, headers=dict(resp.headers), elapsed_ms=round(elapsed, 2), success=True)
            except requests.exceptions.Timeout:
                last_error = 'SSE request timed out'
            except requests.exceptions.ConnectionError:
                last_error = 'SSE connection failed'
            except Exception as e:
                last_error = f'SSE error: {str(e)}'
            if attempt < retries:
                time.sleep(1 * (attempt + 1))
        return BotResponse(status_code=0, raw_body='', reply_text='', headers={}, elapsed_ms=0, error=last_error, success=False)

    def _extract_reply_from_json(self, text: str) -> str:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if self.response_field in data:
                    return str(data[self.response_field])
                for key in ['response', 'reply', 'message', 'text', 'answer', 'output', 'content']:
                    if key in data:
                        return str(data[key])
            return str(data)[:3000]
        except (ValueError, TypeError):
            return text[:3000]

    def wait(self):
        if self.delay > 0:
            time.sleep(self.delay)

class WebSocketSender:

    def __init__(self, url: str, data_field: str='message', response_field: str='response', timeout: int=30, headers: Optional[dict]=None, delay: float=0.5, ws_send_field: str='message', ws_recv_field: str='response', body_data: Optional[dict]=None):
        if not HAS_WEBSOCKETS:
            raise ImportError('websockets library is required for WebSocket scanning. Install with: pip install websockets>=12.0')
        self.url = url
        if self.url.startswith('http://'):
            self.url = 'ws://' + self.url[7:]
        elif self.url.startswith('https://'):
            self.url = 'wss://' + self.url[8:]
        self.data_field = data_field
        self.response_field = response_field
        self.timeout = timeout
        self.delay = delay
        self.ws_send_field = ws_send_field
        self.ws_recv_field = ws_recv_field
        self.body_data = body_data
        self.extra_headers = {'User-Agent': 'LLM-RedTeam-Scanner/1.0'}
        if headers:
            self.extra_headers.update(headers)

    def send(self, message: str, retries: int=2) -> BotResponse:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._send_ws(message, retries))
        finally:
            loop.close()

    async def _send_ws(self, message: str, retries: int) -> BotResponse:
        last_error = None
        for attempt in range(retries + 1):
            try:
                start = time.time()
                chunks = []
                async with websockets.connect(self.url, additional_headers=self.extra_headers, open_timeout=self.timeout, close_timeout=5) as ws:
                    if self.body_data:
                        import copy
                        payload_body = copy.deepcopy(self.body_data)
                        payload_body[self.ws_send_field] = message
                    else:
                        payload_body = {self.ws_send_field: message}
                    payload = json.dumps(payload_body)
                    await ws.send(payload)
                    try:
                        while True:
                            frame = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                            if isinstance(frame, bytes):
                                frame = frame.decode('utf-8', errors='replace')
                            try:
                                data = json.loads(frame)
                                if isinstance(data, dict):
                                    if data.get('done') or data.get('finished'):
                                        if self.ws_recv_field in data:
                                            chunks.append(str(data[self.ws_recv_field]))
                                        break
                                    if self.ws_recv_field in data:
                                        chunks.append(str(data[self.ws_recv_field]))
                                    elif 'content' in data:
                                        chunks.append(str(data['content']))
                                    elif 'text' in data:
                                        chunks.append(str(data['text']))
                                    else:
                                        chunks.append(frame)
                                else:
                                    chunks.append(str(data))
                            except (json.JSONDecodeError, TypeError):
                                chunks.append(frame)
                    except asyncio.TimeoutError:
                        pass
                elapsed = (time.time() - start) * 1000
                full_text = ''.join(chunks) if chunks else ''
                return BotResponse(status_code=200, raw_body=full_text[:5000], reply_text=full_text, headers={}, elapsed_ms=round(elapsed, 2), success=bool(full_text))
            except asyncio.TimeoutError:
                last_error = 'WebSocket connection timed out'
            except ConnectionRefusedError:
                last_error = 'WebSocket connection refused'
            except Exception as e:
                last_error = f'WebSocket error: {str(e)}'
            if attempt < retries:
                await asyncio.sleep(1 * (attempt + 1))
        return BotResponse(status_code=0, raw_body='', reply_text='', headers={}, elapsed_ms=0, error=last_error, success=False)

    def wait(self):
        if self.delay > 0:
            time.sleep(self.delay)