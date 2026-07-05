import argparse
import sys
import json

BANNER = """
  ██▓     ██▓     ███▄ ▄███▓      ██▀███  ▓█████ ▓█████▄ ▄▄▄█████▓▓█████ ▄▄▄       ███▄ ▄███▓
 ▓██▒    ▓██▒    ▓██▒▀█▀ ██▒     ▓██ ▒ ██▒▓█   ▀ ▒██▀ ██▌▓  ██▒ ▓▒▓█   ▀▒████▄    ▓██▒▀█▀ ██▒
 ▒██░    ▒██░    ▓██    ▓██░     ▓██ ░▄█ ▒▒███   ░██   █▌▒ ▓██░ ▒░▒███  ▒██  ▀█▄  ▓██    ▓██░
 ▒██░    ▒██░    ▒██    ▒██      ▒██▀▀█▄  ▒▓█  ▄ ░▓█▄   ▌░ ▓██▓ ░ ▒▓█  ▄░██▄▄▄▄██ ▒██    ▒██
 ░██████▒░██████▒▒██▒   ░██▒     ░██▓ ▒██▒░▒████▒░▒████▓   ▒██▒ ░ ░▒████▒▓█   ▓██▒▒██▒   ░██▒
 ░ ▒░▓  ░░ ▒░▓  ░░ ▒░   ░  ░     ░ ▒▓ ░▒▓░░░ ▒░ ░ ▒▒▓  ▒   ▒ ░░   ░░ ▒░ ░▒▒   ▓▒█░░ ▒░   ░  ░
 ░ ░ ▒  ░░ ░ ▒  ░░  ░      ░       ░▒ ░ ▒░ ░ ░  ░ ░ ▒  ▒     ░     ░ ░  ░ ░   ▒▒ ░░  ░      ░
   ░ ░     ░ ░   ░      ░          ░░   ░    ░    ░ ░  ░   ░         ░    ░   ▒   ░      ░
     ░  ░    ░  ░       ░           ░        ░  ░   ░                 ░  ░     ░  ░       ░
                                                  ░
                      ╔══════════════════════════════════════╗
                      ║  LLM RED TEAM SCANNER v1.0           ║
                      ║  Adaptive Prompt Injection Testing   ║
                      ║  Made by : Ishaani                   ║
                      ║  [ github.com/mindxflayer ]          ║
                      ╚══════════════════════════════════════╝
"""

def parse_headers(header_strings):
    headers = {}
    if header_strings:
        for h in header_strings:
            if ':' in h:
                (key, value) = h.split(':', 1)
                headers[key.strip()] = value.strip()
    return headers

def main():
    print(BANNER)
    parser = argparse.ArgumentParser(prog='LLM Red Team Scanner', description=' Adaptive Prompt Injection Testing Tool for LLM Chatbots (v1.0)', formatter_class=argparse.RawDescriptionHelpFormatter, epilog='\nExamples:\n  # Basic scan\n  python tool.py -u http://localhost:5000/chat -m POST -d message -t json\n\n  # Fast concurrent scan with evasion\n  python tool.py -u http://localhost:5000/chat -m POST -d message -t json --concurrency 10 --evasion\n\n  # Full attack suite with fuzzing and multi-turn\n  python tool.py -u http://localhost:5000/chat -m POST -d message -t json --multi-turn --fuzz --evasion\n\n  # With LLM judge for false-positive reduction\n  python tool.py -u http://localhost:5000/chat -m POST -d message -t json --judge-url http://localhost:11434/api/generate --judge-model llama3\n\n  # SSE streaming target\n  python tool.py -u https://api.example.com/chat -m POST -d message -t json --transport sse\n\n  # WebSocket target\n  python tool.py -u ws://localhost:8080/ws -m POST -d message -t json --transport ws\n\nReport Output:\n  Reports are saved to ./reports/ as both HTML and JSON files.\n  Open the HTML file in a browser for an interactive dashboard.\n        ')
    parser.add_argument('-u', '--url', required=True, help='Target chatbot API URL (e.g. http://localhost:5000/chat)')
    req_group = parser.add_argument_group('Request Configuration')
    req_group.add_argument('-m', '--method', default='POST', choices=['GET', 'POST', 'PUT', 'PATCH'], help='HTTP method (default: POST)')
    req_group.add_argument('-d', '--data-field', default='message', help='JSON key for the message field sent to the bot (default: message)')
    req_group.add_argument('-r', '--response-field', default='response', help="JSON key containing the bot's reply in response (default: response)")
    req_group.add_argument('-t', '--content-type', default='json', choices=['json', 'form'], help='Request content type (default: json)')
    req_group.add_argument('--headers', nargs='*', metavar='KEY:VALUE', help='Extra headers as Key:Value pairs (e.g. Authorization:Bearer\\ token123)')
    req_group.add_argument('--body-data', help='JSON string containing additional static post body data (e.g. \'{"action": "chat", "session_id": "123"}\')')
    scan_group = parser.add_argument_group('Scan Configuration')
    scan_group.add_argument('--max-payloads', type=int, default=200, help='Max payloads to test per corpus (default: 200)')
    scan_group.add_argument('--delay', type=float, default=0.5, help='Seconds between requests in sequential mode (default: 0.5)')
    scan_group.add_argument('--timeout', type=int, default=30, help='Request timeout in seconds (default: 30)')
    perf_group = parser.add_argument_group('Concurrency & Performance')
    perf_group.add_argument('--concurrency', type=int, default=1, help='Concurrent requests (default: 1 = sequential). Requires aiohttp.')
    perf_group.add_argument('--rate-limit', type=float, default=10.0, help='Max requests/sec when using concurrency (default: 10.0)')
    judge_group = parser.add_argument_group('LLM-as-a-Judge (false positive reduction)')
    judge_group.add_argument('--judge-url', help='Judge LLM API URL (e.g. http://localhost:11434/api/generate or https://api.openai.com/v1)')
    judge_group.add_argument('--judge-model', default='gpt-4o-mini', help='Judge model name (default: gpt-4o-mini)')
    judge_group.add_argument('--judge-api-key', help='API key for authenticated judge endpoints')
    mt_group = parser.add_argument_group('Multi-Turn Attacks')
    mt_group.add_argument('--multi-turn', action='store_true', help='Enable multi-turn stateful attack chains')
    mt_group.add_argument('--multi-turn-chains', nargs='*', choices=['rapport', 'game', 'persona', 'continuation'], help='Specific chain types to use (default: all)')
    evasion_group = parser.add_argument_group('WAF & Filter Evasion')
    evasion_group.add_argument('--evasion', action='store_true', help='Enable WAF evasion encodings (Base64, Leetspeak, Unicode, etc.)')
    transport_group = parser.add_argument_group('Transport / Streaming')
    transport_group.add_argument('--transport', default='rest', choices=['rest', 'sse', 'ws'], help='Response transport type (default: rest)')
    transport_group.add_argument('--ws-send-field', default='message', help='WebSocket JSON send field name (default: message)')
    transport_group.add_argument('--ws-recv-field', default='response', help='WebSocket JSON receive field name (default: response)')
    fuzz_group = parser.add_argument_group('Genetic Payload Fuzzing')
    fuzz_group.add_argument('--fuzz', action='store_true', help='Enable genetic fuzzing of high-scoring payloads')
    fuzz_group.add_argument('--fuzz-generations', type=int, default=3, help='Number of fuzzing evolution rounds (default: 3)')
    fuzz_group.add_argument('--fuzz-population', type=int, default=10, help='Fuzzing population size per generation (default: 10)')
    out_group = parser.add_argument_group('Output')
    out_group.add_argument('-o', '--output', default='./reports', help='Output report directory (default: ./reports)')
    out_group.add_argument('-v', '--verbose', action='store_true', help='Verbose output — show full responses during scan')
    args = parser.parse_args()
    from core.scanner import Scanner
    body_data = None
    if args.body_data:
        body_str = args.body_data.strip()
        if body_str.startswith("'") and body_str.endswith("'"):
            body_str = body_str[1:-1].strip()
        try:
            body_data = json.loads(body_str)
        except json.JSONDecodeError:
            body_data = {}
            import csv
            try:
                reader = csv.reader([body_str], delimiter=',', quotechar='"', skipinitialspace=True)
                for row in reader:
                    for pair in row:
                        if ':' in pair:
                            k, v = pair.split(':', 1)
                            body_data[k.strip()] = v.strip()
                        elif '=' in pair:
                            k, v = pair.split('=', 1)
                            body_data[k.strip()] = v.strip()
            except Exception:
                pass
            if not body_data:
                parser.error("Invalid JSON or Key:Value pairs in --body-data. Ensure proper formatting.")
    headers = parse_headers(args.headers)
    scanner = Scanner(url=args.url, method=args.method, data_field=args.data_field, response_field=args.response_field, content_type=args.content_type, max_payloads=args.max_payloads, delay=args.delay, timeout=args.timeout, headers=headers, output_dir=args.output, verbose=args.verbose, concurrency=args.concurrency, rate_limit=args.rate_limit, transport=args.transport, ws_send_field=args.ws_send_field, ws_recv_field=args.ws_recv_field, evasion=args.evasion, multi_turn=args.multi_turn, multi_turn_chains=args.multi_turn_chains, fuzz=args.fuzz, fuzz_generations=args.fuzz_generations, fuzz_population=args.fuzz_population, judge_url=args.judge_url, judge_model=args.judge_model, judge_api_key=args.judge_api_key, body_data=body_data)
    try:
        scanner.run()
    except KeyboardInterrupt:
        print('\n\n  Scan interrupted by user.')
        sys.exit(1)
    except Exception as e:
        print(f'\n Fatal error: {e}')
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
if __name__ == '__main__':
    main()