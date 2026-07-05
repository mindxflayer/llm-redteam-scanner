import json
import os
from datetime import datetime
from typing import List
from core.analyzer import Finding, CONFIRMED, LIKELY, POSSIBLE, SAFE, SEVERITY_SCORE
from core.recon import ReconProfile

class Reporter:

    def __init__(self, output_dir: str='./reports'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, findings: List[Finding], profile: ReconProfile, target_url: str, scan_duration: float) -> str:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_path = os.path.join(self.output_dir, f'report_{timestamp}.json')
        html_path = os.path.join(self.output_dir, f'report_{timestamp}.html')
        report_data = self._build_report_data(findings, profile, target_url, scan_duration)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f'  JSON report: {json_path}')
        html = self._render_html(report_data)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'  HTML report: {html_path}')
        return html_path

    def _build_report_data(self, findings: List[Finding], profile: ReconProfile, target_url: str, scan_duration: float) -> dict:
        severity_counts = {CONFIRMED: 0, LIKELY: 0, POSSIBLE: 0, SAFE: 0}
        family_stats = {}
        for f in findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
            fam = f.family
            if fam not in family_stats:
                family_stats[fam] = {CONFIRMED: 0, LIKELY: 0, POSSIBLE: 0, SAFE: 0}
            family_stats[fam][f.severity] += 1
        if severity_counts[CONFIRMED] >= 3:
            risk_rating = 'CRITICAL'
        elif severity_counts[CONFIRMED] >= 1 or severity_counts[LIKELY] >= 5:
            risk_rating = 'HIGH'
        elif severity_counts[LIKELY] >= 1 or severity_counts[POSSIBLE] >= 5:
            risk_rating = 'MEDIUM'
        elif severity_counts[POSSIBLE] >= 1:
            risk_rating = 'LOW'
        else:
            risk_rating = 'PASS'
        return {'scan_metadata': {'tool': 'LLM Red Team Scanner', 'version': '1.0.0', 'timestamp': datetime.now().isoformat(), 'target_url': target_url, 'scan_duration_seconds': round(scan_duration, 2), 'total_payloads_tested': len(findings), 'features_used': self._detect_features(findings)}, 'risk_rating': risk_rating, 'severity_summary': severity_counts, 'family_breakdown': family_stats, 'recon_profile': {'domain': profile.domain, 'stated_purpose': profile.stated_purpose, 'bot_name': profile.bot_name, 'tone': profile.tone, 'topics': profile.topics, 'keywords': profile.keywords[:15], 'has_guardrails': profile.has_guardrails, 'boundary_softness': profile.boundary_softness, 'capabilities': profile.capabilities}, 'findings': [{'payload_id': f.payload_id, 'family': f.family, 'strategy': f.strategy, 'severity': f.severity, 'score': f.score, 'signals': f.signals, 'original_payload': f.original_payload, 'adapted_payload': f.adapted_payload, 'response': f.response, 'elapsed_ms': f.elapsed_ms} for f in sorted(findings, key=lambda x: x.score, reverse=True)]}

    def _detect_features(self, findings: List[Finding]) -> List[str]:
        features = []
        strategies = set((f.strategy for f in findings))
        signals_flat = ' '.join((' '.join(f.signals) for f in findings))
        if any(('multi_turn' in s for s in strategies)):
            features.append('Multi-Turn Attacks')
        if any(('fuzz_gen' in s for s in strategies)):
            features.append('Genetic Fuzzing')
        if 'JUDGE_UPGRADED' in signals_flat or 'JUDGE_DOWNGRADED' in signals_flat:
            features.append('LLM Judge')
        if any((hasattr(f, 'adapted_payload') and ('Base64' in f.adapted_payload or 'ROT13' in f.adapted_payload) for f in findings[:50])):
            features.append('WAF Evasion')
        return features

    def _render_html(self, data: dict) -> str:
        risk = data['risk_rating']
        sev = data['severity_summary']
        meta = data['scan_metadata']
        recon = data['recon_profile']
        findings = data['findings']
        risk_borders = {'CRITICAL': '#ffffff', 'HIGH': '#aaaaaa', 'MEDIUM': '#888888', 'LOW': '#444444', 'PASS': '#222222'}
        sev_styles = {
            CONFIRMED: 'background: #ffffff; color: #000000; border: 1px solid #ffffff;',
            LIKELY: 'background: #cccccc; color: #000000; border: 1px solid #ccccccc;',
            POSSIBLE: 'background: #555555; color: #ffffff; border: 1px solid #555555;',
            SAFE: 'background: #000000; color: #888888; border: 1px solid #333333;',
        }
        findings_html = ''
        for (i, f) in enumerate(findings):
            sev_label = f['severity']
            badge_style = sev_styles.get(sev_label, 'background: #333333; color: #ffffff; border: 1px solid #333333;')
            signals_str = '<br>'.join(f['signals'])
            orig_payload = f.get('original_payload', '')
            bot_resp = f.get('response', '')
            
            orig_preview = self._escape_html(orig_payload)
            if len(orig_preview) > 50:
                orig_preview = orig_preview[:47] + '...'
            resp_preview = self._escape_html(bot_resp)
            if len(resp_preview) > 50:
                resp_preview = resp_preview[:47] + '...'
                
            findings_html += f"""
            <tr class="finding-row" onclick="toggleDetail('detail-{i}', {i})">
                <td>{f['payload_id']}</td>
                <td><span class="badge" style="{badge_style}">{sev_label}</span></td>
                <td>{f['score']}</td>
                <td><code>{f['family']}</code></td>
                <td><code>{f['strategy']}</code></td>
                <td class="payload-cell">{orig_preview}</td>
                <td class="response-cell">{resp_preview}</td>
                <td>{f['elapsed_ms']:.0f}ms</td>
                <td><span class="chevron" id="chevron-{i}">▼</span></td>
            </tr>
            <tr id="detail-{i}" class="detail-row" style="display:none">
                <td colspan="9">
                    <div class="detail-box">
                        <div class="detail-section">
                            <strong>Signals:</strong><br>{signals_str}
                        </div>
                        <div class="detail-section">
                            <strong>Original Payload:</strong>
                            <pre>{self._escape_html(orig_payload)}</pre>
                        </div>
                        <div class="detail-section">
                            <strong>Adapted Payload:</strong>
                            <pre>{self._escape_html(f.get('adapted_payload', ''))}</pre>
                        </div>
                        <div class="detail-section">
                            <strong>Bot Response:</strong>
                            <pre>{self._escape_html(bot_resp)}</pre>
                        </div>
                    </div>
                </td>
            </tr>
            """
        family_html = ''
        for (fam, counts) in data.get('family_breakdown', {}).items():
            total = sum(counts.values())
            bad = counts.get(CONFIRMED, 0) + counts.get(LIKELY, 0)
            pct = bad / total * 100 if total > 0 else 0
            bar_color = '#ffffff' if pct > 20 else '#888888' if pct > 5 else '#333333'
            family_html += f"""
            <div class="family-item">
                <div class="family-name"><code>{fam}</code></div>
                <div class="family-bar-wrap">
                    <div class="family-bar" style="width:{pct:.0f}%; background:{bar_color}"></div>
                </div>
                <div class="family-stats">{bad}/{total} ({pct:.0f}%)</div>
            </div>
            """
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LLM Red Team Scan Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        background: #000000; color: #ffffff;
        line-height: 1.6;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    
    /* Header */
    .header {{
        background: #000000;
        border: 1px solid #333333; border-radius: 12px;
        padding: 32px; margin-bottom: 24px;
    }}
    .header h1 {{
        font-size: 28px; font-weight: 700;
        color: #ffffff;
    }}
    .header .subtitle {{ color: #888888; margin-top: 4px; }}
    
    /* Risk badge */
    .risk-banner {{
        background: #000000;
        border: 2px solid {risk_borders.get(risk, '#ffffff')};
        border-radius: 12px; padding: 24px;
        text-align: center; margin-bottom: 24px;
    }}
    .risk-label {{ font-size: 14px; color: #888888; text-transform: uppercase; letter-spacing: 2px; }}
    .risk-value {{
        font-size: 48px; font-weight: 800;
        color: #ffffff;
        margin: 8px 0;
    }}
    
    /* Stat cards */
    .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .stat-card {{
        background: #000000; border: 1px solid #333333;
        border-radius: 10px; padding: 20px; text-align: center;
    }}
    .stat-number {{ font-size: 32px; font-weight: 700; color: #ffffff; }}
    .stat-label {{ font-size: 12px; color: #888888; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }}
    
    /* Sections */
    .section {{
        background: #000000; border: 1px solid #333333;
        border-radius: 12px; padding: 24px; margin-bottom: 24px;
    }}
    .section h2 {{
        font-size: 18px; margin-bottom: 16px;
        padding-bottom: 8px; border-bottom: 1px solid #333333;
    }}
    
    /* Recon grid */
    .recon-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .recon-item {{ padding: 8px 0; }}
    .recon-item .label {{ color: #888888; font-size: 12px; text-transform: uppercase; }}
    .recon-item .value {{ color: #ffffff; font-weight: 500; }}
    .keyword-tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .keyword-tag {{
        background: #111111; border: 1px solid #333333; padding: 4px 10px; border-radius: 20px;
        font-size: 12px; color: #888888;
    }}
    
    /* Family breakdown */
    .family-item {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
    .family-name {{ width: 180px; text-align: right; }}
    .family-bar-wrap {{ flex: 1; height: 20px; background: #111111; border: 1px solid #333333; border-radius: 4px; overflow: hidden; }}
    .family-bar {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
    .family-stats {{ width: 100px; font-size: 13px; color: #888888; }}
    
    /* Findings table */
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; padding: 12px; color: #888888; font-size: 12px;
        text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #333333; }}
    .finding-row td {{ padding: 12px; border-bottom: 1px solid #111111; cursor: pointer; }}
    .finding-row:hover {{ background: #111111; }}
    .badge {{
        padding: 3px 10px; border-radius: 20px; font-size: 11px;
        font-weight: 700; text-transform: uppercase;
    }}
    .payload-cell, .response-cell {{
        max-width: 220px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 12px;
        color: #cccccc;
    }}
    .chevron {{
        transition: transform 0.2s;
        display: inline-block;
        color: #888;
        font-size: 10px;
    }}
    .detail-row td {{ padding: 0; }}
    .detail-box {{ background: #070709; padding: 24px; border-left: 4px solid #ffffff; margin: 10px 0; border-radius: 0 8px 8px 0; }}
    .detail-section {{ margin-bottom: 16px; }}
    .detail-section strong {{ font-size: 13px; text-transform: uppercase; color: #888; letter-spacing: 0.5px; }}
    .detail-section pre {{
        background: #111115; border: 1px solid #22222b; padding: 16px; border-radius: 8px;
        white-space: pre-wrap; word-break: break-word;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 13px; margin-top: 6px; max-height: 350px; overflow-y: auto; color: #e0e0e6;
    }}
    code {{ background: #111115; border: 1px solid #22222b; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
    
    .footer {{ text-align: center; padding: 24px; color: #888888; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>LLM Red Team Scan Report</h1>
        <div class="subtitle">Target: <code>{self._escape_html(meta['target_url'])}</code> &nbsp;|&nbsp;
        {meta['timestamp'][:19]} &nbsp;|&nbsp; {meta['scan_duration_seconds']}s</div>
    </div>
    
    <div class="risk-banner">
        <div class="risk-label">Overall Risk Rating</div>
        <div class="risk-value">{risk}</div>
        <div style="color:#888888">{meta['total_payloads_tested']} payloads tested across {len(data.get('family_breakdown', {}))} attack families</div>
    </div>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number">{sev.get(CONFIRMED, 0)}</div>
            <div class="stat-label">Confirmed</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{sev.get(LIKELY, 0)}</div>
            <div class="stat-label">Likely</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{sev.get(POSSIBLE, 0)}</div>
            <div class="stat-label">Possible</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{sev.get(SAFE, 0)}</div>
            <div class="stat-label">Safe</div>
        </div>
    </div>
    
    <div class="section">
        <h2>Recon Profile</h2>
        <div class="recon-grid">
            <div class="recon-item"><div class="label">Domain</div><div class="value">{recon.get('domain', 'N/A')}</div></div>
            <div class="recon-item"><div class="label">Bot Name</div><div class="value">{recon.get('bot_name', 'N/A') or 'N/A'}</div></div>
            <div class="recon-item"><div class="label">Purpose</div><div class="value">{self._escape_html(recon.get('stated_purpose', 'N/A')[:150])}</div></div>
            <div class="recon-item"><div class="label">Tone</div><div class="value">{recon.get('tone', 'N/A')}</div></div>
            <div class="recon-item"><div class="label">Guardrails</div><div class="value">{('Yes (' + recon.get('boundary_softness', '') + ')' if recon.get('has_guardrails') else 'No / Not Detected')}</div></div>
            <div class="recon-item"><div class="label">Capabilities</div><div class="value">{', '.join(recon.get('capabilities', [])) or 'N/A'}</div></div>
        </div>
        <div style="margin-top: 12px;">
            <div class="label" style="color:#888888; font-size:12px; text-transform:uppercase; margin-bottom: 8px;">Extracted Keywords</div>
            <div class="keyword-tags">
                {''.join((f'<span class="keyword-tag">{self._escape_html(kw)}</span>' for kw in recon.get('keywords', [])[:15]))}
            </div>
        </div>
    </div>
    
    <div class="section">
        <h2>Attack Family Breakdown</h2>
        <div style="margin-top: 12px;">
            {family_html}
        </div>
    </div>
    
    <div class="section">
        <h2>Detailed Findings</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th><th>Severity</th><th>Score</th>
                    <th>Family</th><th>Strategy</th><th>Original Payload (Preview)</th>
                    <th>Bot Response (Preview)</th><th>Latency</th><th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {findings_html}
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        Generated by LLM Red Team Scanner v1.0.0 &nbsp;|&nbsp; For authorized security testing only
    </div>
</div>

<script>
function toggleDetail(id, idx) {{
    const row = document.getElementById(id);
    const chevron = document.getElementById('chevron-' + idx);
    if (row.style.display === 'none') {{
        row.style.display = 'table-row';
        if (chevron) chevron.style.transform = 'rotate(180deg)';
    }} else {{
        row.style.display = 'none';
        if (chevron) chevron.style.transform = 'rotate(0deg)';
    }}
}}
</script>
</body>
</html>"""
        return html

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')