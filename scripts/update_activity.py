#!/usr/bin/env python3
"""Export the signed-in Codex profile's aggregate token statistics only.

Uses a private desktop endpoint, observed in the installed app on 2026-09-14.
It may change. On authentication/schema errors, leave the previous card intact.
No third-party dependencies; credentials never leave this Mac except to ChatGPT.
"""
import argparse
import colorsys
import datetime as dt
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://chatgpt.com/backend-api/wham/profiles/me'
REPOSITORY = 'liilymiao/liilymiao'
OUTPUTS = ('data/token-activity.json', 'assets/token-activity.svg',
           'assets/token-activity-dark.svg')


def integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError('Invalid nonnegative integer: ' + name)
    return value


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError('Missing source date')
    parsed = dt.date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('Invalid source date format')
    return value


def sanitize(response, expected_profile):
    if response.get('profile', {}).get('username') != expected_profile:
        raise ValueError('Signed-in Codex profile does not match expected profile')
    meta = response['metadata']
    if meta.get('stats_error'):
        raise ValueError('Codex reports statistics unavailable')
    as_of = iso_date(meta['stats_as_of'])
    stats = response['stats']
    names = ('lifetime_tokens', 'peak_daily_tokens', 'current_streak_days',
             'longest_streak_days')
    summary = {name: integer(stats[name], name) for name in names}
    raw = stats['daily_usage_buckets']
    if not isinstance(raw, list) or not raw:
        raise ValueError('Daily token history is unavailable')
    daily = []
    seen = set()
    for bucket in raw:
        date = iso_date(bucket['start_date'])
        if date in seen or date > as_of:
            raise ValueError('Duplicate or future daily bucket')
        seen.add(date)
        daily.append({'date': date, 'tokens': integer(bucket['tokens'], 'tokens')})
    daily.sort(key=lambda row: row['date'])
    # The present endpoint returns full daily history. Reject a changed/truncated
    # schema rather than silently publishing a graph with missing activity.
    if sum(row['tokens'] for row in daily) != summary['lifetime_tokens']:
        raise ValueError('Daily history does not reconcile with lifetime tokens')
    if max(row['tokens'] for row in daily) != summary['peak_daily_tokens']:
        raise ValueError('Daily peak does not reconcile with source summary')
    if summary['current_streak_days'] > summary['longest_streak_days']:
        raise ValueError('Invalid streak summary')
    return {'schema_version': 1, 'source': 'Codex profile statistics',
            'stats_as_of': as_of,
            'date_basis': 'Source-provided dates; no timezone conversion',
            'summary': summary, 'daily': daily}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Unexpected redirect from statistics endpoint')


def fetch_usage(codex_dir, expected_profile):
    with (codex_dir / 'auth.json').open() as stream:
        tokens = json.load(stream)['tokens']
    access = tokens.get('access_token')
    if not access:
        raise ValueError('Sign in to Codex on this Mac before updating')
    headers = {'Authorization': 'Bearer ' + access,
               'Accept': 'application/json',
               'User-Agent': 'Codex-token-activity-export/1.0'}
    if tokens.get('account_id'):
        headers['ChatGPT-Account-Id'] = tokens['account_id']
    request = urllib.request.Request(ENDPOINT, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        payload = json.load(response)
    return sanitize(payload, expected_profile)


def compact(number):
    for divisor, suffix in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if number >= divisor:
            return ('%.2f' % (number / divisor)).rstrip('0').rstrip('.') + suffix
    return str(number)


def level(tokens, peak):
    if not tokens or not peak:
        return 0
    return 4 if tokens > peak * .75 else 3 if tokens > peak * .5 else 2 if tokens > peak * .25 else 1


def rainbow(position, dark=False):
    # Hue advances across the visible active dates; intensity encodes usage.
    hue = (8 + 272 * max(0, min(1, position))) / 360
    rgb = colorsys.hls_to_rgb(hue, .65 if dark else .52, .78)
    return '#' + ''.join(f'{round(channel * 255):02x}' for channel in rgb)


def render(data, dark=False):
    if dark:
        bg, border, fg, muted, panel = '#0d1117', '#30363d', '#e6edf3', '#919ba8', '#161b22'
        empty = '#21262d'
    else:
        bg, border, fg, muted, panel = '#ffffff', '#dce2ea', '#1f2937', '#687386', '#f7f9fc'
        empty = '#eef1f5'
    intensities = (0, .38, .58, .79, 1)
    as_of = dt.date.fromisoformat(data['stats_as_of'])
    sunday = as_of - dt.timedelta(days=(as_of.weekday() + 1) % 7)
    start = sunday - dt.timedelta(weeks=51)
    values = {row['date']: row['tokens'] for row in data['daily']}
    peak = max((v for k, v in values.items() if start.isoformat() <= k <= as_of.isoformat()), default=0)
    active = [dt.date.fromisoformat(k) for k, v in values.items()
              if v > 0 and start.isoformat() <= k <= as_of.isoformat()]
    first_active = min(active, default=start)
    active_span = max(1, (max(active, default=as_of) - first_active).days)
    summary = data['summary']
    e = html.escape
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="356" viewBox="0 0 900 356" role="img" aria-labelledby="title desc">',
             '<title id="title">Codex token activity</title>',
             f'<desc id="desc">Statistics as of {as_of}: {summary["lifetime_tokens"]:,} lifetime tokens, {summary["peak_daily_tokens"]:,} peak daily tokens, {summary["current_streak_days"]} day current streak. Rainbow hue progresses across active dates; color intensity indicates daily token usage. Exact counts appear in cell titles.</desc>',
             f'<rect x="0.5" y="0.5" width="899" height="355" rx="18" fill="{bg}" stroke="{border}"/>',
             '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">']

    def text(x, y, value, size=12, color=muted, weight=400, extra=''):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" {extra}>{e(str(value))}</text>')

    text(28, 39, 'TOKEN ACTIVITY', 17, fg, 650, 'letter-spacing="1.3"')
    text(872, 39, 'CODEX  /  @liilymiao', 12, muted, 500, 'text-anchor="end"')
    parts.append(f'<rect x="28" y="59" width="844" height="80" rx="12" fill="{panel}"/>')
    metrics = [('LIFETIME TOKENS', compact(summary['lifetime_tokens']), f'{summary["lifetime_tokens"]:,} tokens'),
               ('PEAK DAY', compact(summary['peak_daily_tokens']), f'{summary["peak_daily_tokens"]:,} tokens'),
               ('CURRENT STREAK', str(summary['current_streak_days']) + ' days', 'Source-reported consecutive days'),
               ('LONGEST STREAK', str(summary['longest_streak_days']) + ' days', 'Source-reported consecutive days')]
    for index, (label, value, title) in enumerate(metrics):
        x = 48 + index * 211
        parts.append(f'<g><title>{e(title)}</title>')
        text(x, 90, value, 25, fg, 600)
        text(x, 116, label, 10, muted, 500, 'letter-spacing=".7"')
        parts.append('</g>')
    grid_x, grid_y, step, cell = 77, 186, 15, 11
    month = None
    for week in range(52):
        day = start + dt.timedelta(weeks=week)
        if day.month != month:
            text(grid_x + week * step, 174, day.strftime('%b'), 11)
            month = day.month
    for row, label in ((1, 'Mon'), (3, 'Wed'), (5, 'Fri')):
        text(31, grid_y + row * step + 9, label, 10)
    for index in range(52 * 7):
        day = start + dt.timedelta(days=index)
        if day > as_of:
            continue
        tokens = values.get(day.isoformat(), 0)
        x, y = grid_x + index // 7 * step, grid_y + index % 7 * step
        color = rainbow((day - first_active).days / active_span, dark) if tokens else empty
        opacity = intensities[level(tokens, peak)] if tokens else 1
        parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{color}" fill-opacity="{opacity}"><title>{day.isoformat()}: {tokens:,} tokens</title></rect>')
    text(28, 326, 'Statistics as of ' + as_of.isoformat(), 11)
    text(450, 326, 'Daily tokens · past 52 weeks', 11, muted, 400, 'text-anchor="middle"')
    text(732, 326, 'Less', 10)
    stops = ''.join(f'<stop offset="{i / 6:.3f}" stop-color="{rainbow(i / 6, dark)}"/>' for i in range(7))
    parts.append(f'<defs><linearGradient id="rainbow-key">{stops}</linearGradient></defs>')
    for i, opacity in enumerate(intensities):
        color = 'url(#rainbow-key)' if i else empty
        parts.append(f'<rect x="{763+i*15}" y="317" width="11" height="11" rx="3" fill="{color}" fill-opacity="{opacity if i else 1}"/>')
    text(842, 326, 'More', 10)
    parts.append('</g></svg>')
    svg = '\n'.join(parts) + '\n'
    ET.fromstring(svg)
    return svg


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True,
                                   stderr=subprocess.PIPE, timeout=60).strip()


def publish_ready():
    if git('status', '--porcelain'):
        raise ValueError('Working tree contains changes; refusing automatic publish')
    if git('branch', '--show-current') != 'main':
        raise ValueError('Automatic publishing requires the main branch')
    remote = git('remote', 'get-url', 'origin')
    if remote not in ('git@github.com:' + REPOSITORY + '.git',
                      'ssh://git@ssh.github.com:443/' + REPOSITORY + '.git',
                      'https://github.com/' + REPOSITORY + '.git'):
        raise ValueError('Unexpected publishing repository')
    git('pull', '--ff-only', 'origin', 'main')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-profile', required=True)
    parser.add_argument('--codex-dir', type=Path, default=Path.home() / '.codex')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.publish:
        publish_ready()
    data = fetch_usage(args.codex_dir, args.expected_profile)
    rendered = (json.dumps(data, indent=2, ensure_ascii=False) + '\n', render(data), render(data, True))
    changed = []
    # Validate the complete response and both SVGs before replacing any artifact.
    for relative, content in zip(OUTPUTS, rendered):
        path = ROOT / relative
        if path.exists() and path.read_text() == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(content)
        os.replace(temporary, path)
        changed.append(relative)
    if args.publish and changed:
        git('add', '--', *OUTPUTS)
        git('commit', '-m', 'Update Codex token activity: ' + data['stats_as_of'])
    if args.publish:
        # Also retries a preceding push failure with a clean local commit.
        git('push', 'origin', 'main')
        local = git('rev-parse', 'HEAD')
        remote = git('ls-remote', 'origin', 'refs/heads/main').split()[0]
        if local != remote:
            raise ValueError('Published revision could not be verified')
    print(json.dumps({'changed': changed, 'stats_as_of': data['stats_as_of'],
                      'lifetime_tokens': data['summary']['lifetime_tokens'],
                      'published': args.publish}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        print('Statistics request failed (HTTP %d); previous card preserved. Check Codex sign-in.' % error.code, file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        # Never log request headers, authentication responses, or raw API bodies.
        print('Update failed: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
