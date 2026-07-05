import time
import requests
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class BotResponse:
    status_code: int
    raw_body: str
    reply_text: str
    headers: dict
    elapsed_ms: float
    error: Optional[str] = None
    success: bool = True

class Sender:

    def __init__(self, url: str, method: str='POST', data_field: str='message', response_field: str='response', content_type: str='json', timeout: int=30, headers: Optional[dict]=None, delay: float=0.5, transport: str='rest', ws_send_field: str='message', ws_recv_field: str='response', body_data: Optional[dict]=None):
        self.url = url
        self.method = method.upper()
        self.data_field = data_field
        self.response_field = response_field
        self.content_type = content_type
        self.timeout = timeout
        self.delay = delay
        self.transport = transport
        self.body_data = body_data
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'LLM-RedTeam-Scanner/1.0'})
        if headers:
            self.session.headers.update(headers)
        self._stream_sender = None
        if transport == 'sse':
            from core.stream_sender import SSESender
            self._stream_sender = SSESender(url=url, method=method, data_field=data_field, response_field=response_field, content_type=content_type, timeout=timeout, headers=headers, delay=delay, body_data=body_data)
        elif transport == 'ws':
            from core.stream_sender import WebSocketSender
            self._stream_sender = WebSocketSender(url=url, data_field=data_field, response_field=response_field, timeout=timeout, headers=headers, delay=delay, ws_send_field=ws_send_field, ws_recv_field=ws_recv_field, body_data=body_data)

    def send(self, message: str, retries: int=2) -> BotResponse:
        if self._stream_sender:
            return self._stream_sender.send(message, retries=retries)
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
        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = self.session.request(self.method, self.url, **kwargs)
                elapsed = resp.elapsed.total_seconds() * 1000
                reply_text = self._extract_reply(resp)
                return BotResponse(status_code=resp.status_code, raw_body=resp.text[:5000], reply_text=reply_text, headers=dict(resp.headers), elapsed_ms=round(elapsed, 2), success=True)
            except requests.exceptions.Timeout:
                last_error = 'Request timed out'
            except requests.exceptions.ConnectionError:
                last_error = 'Connection refused or failed'
            except requests.exceptions.RequestException as e:
                last_error = str(e)
            if attempt < retries:
                time.sleep(1 * (attempt + 1))
        return BotResponse(status_code=0, raw_body='', reply_text='', headers={}, elapsed_ms=0, error=last_error, success=False)

    def _extract_reply(self, resp: requests.Response) -> str:
        try:
            data = resp.json()
        except (ValueError, TypeError):
            return resp.text[:3000]
        if isinstance(data, dict):
            if self.response_field in data:
                val = data[self.response_field]
                return str(val) if not isinstance(val, str) else val
            common_fields = ['response', 'reply', 'message', 'text', 'answer', 'output', 'content', 'result', 'data', 'bot_response', 'bot_reply', 'assistant', 'completion', 'generated_text']
            for key in common_fields:
                if key in data:
                    val = data[key]
                    if isinstance(val, str):
                        return val
                    elif isinstance(val, dict):
                        for inner_key in ['content', 'text', 'message']:
                            if inner_key in val:
                                return str(val[inner_key])
                    elif isinstance(val, list) and val:
                        first = val[0]
                        if isinstance(first, str):
                            return first
                        elif isinstance(first, dict):
                            for inner_key in ['content', 'text', 'message']:
                                if inner_key in first:
                                    return str(first[inner_key])
            if 'choices' in data and isinstance(data['choices'], list):
                for choice in data['choices']:
                    if isinstance(choice, dict):
                        msg = choice.get('message', choice.get('delta', {}))
                        if isinstance(msg, dict) and 'content' in msg:
                            return str(msg['content'])
            return str(data)[:3000]
        return resp.text[:3000]

    def wait(self):
        if self.delay > 0:
            time.sleep(self.delay)