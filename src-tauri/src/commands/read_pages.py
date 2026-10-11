"""Read bounded public webpages without running scripts or following redirects."""
import codecs
import concurrent.futures
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
from urllib.parse import quote, urlsplit
from lxml import html


def public_target(address):
    url = urlsplit(address)
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username
            or url.password or url.port not in (None, 80 if url.scheme == 'http' else 443)):
        raise ValueError('not a public HTTP(S) URL')
    host = url.hostname.encode('idna').decode('ascii')
    port = url.port or (443 if url.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any((not ipaddress.ip_address(a[4][0]).is_global or ipaddress.ip_address(a[4][0]).is_multicast) for a in addresses):
        raise ValueError('local, private or reserved network address')
    # Pin the checked address so a second DNS lookup cannot redirect the request into a private network.
    ip = sorted(addresses, key=lambda a: a[0] != socket.AF_INET)[0][4][0]
    return url, host, port, ip


def fetch(address):
    url, host, port, ip = public_target(address)
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.sock = socket.create_connection((ip, port), timeout=10)
    try:
        if url.scheme == 'https':
            connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=host)
        # HTTP request targets must be ASCII; keep existing escapes and URI delimiters.
        target = quote(url.path or '/', safe="/%:@!$&'()*+,;=")
        if url.query:
            target += '?' + quote(url.query, safe="/%?:@!$&'()*+,;=")
        connection.request('GET', target, headers={'User-Agent': 'C-manager/0.1', 'Accept': 'text/html', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}; redirects are not followed')
        if 'text/html' not in response.getheader('Content-Type', '').lower():
            raise ValueError('not HTML')
        body = response.read(1_048_577)
        if len(body) > 1_048_576:
            raise ValueError('page exceeds 1 MiB')
        return decode_html(body, response.headers.get_content_charset())
    finally:
        connection.close()


def decode_html(body, charset=None):
    # Decode before lxml: HTML5 charset declarations are not reliably detected by libxml2.
    for bom, encoding in [(codecs.BOM_UTF32_LE, 'utf-32'), (codecs.BOM_UTF32_BE, 'utf-32'),
                          (codecs.BOM_UTF8, 'utf-8-sig'),
                          (codecs.BOM_UTF16_LE, 'utf-16'), (codecs.BOM_UTF16_BE, 'utf-16')]:
        if body.startswith(bom):
            return body.decode(encoding)
    if not charset:
        for tag in re.findall(br'<meta\b[^>]*>', body[:8192], re.I):
            match = re.search(br'\bcharset\s*=\s*[\"\']?([a-zA-Z0-9._-]+)', tag, re.I)
            if match:
                charset = match[1].decode('ascii')
                break
    # Fail on invalid bytes instead of feeding replacement characters to the model.
    return body.decode(charset or 'utf-8')


def excerpt(body, query, local_path="", require_match=False):
    document = html.fromstring(decode_html(body) if isinstance(body, bytes) else body)
    for node in document.xpath('//script|//style|//nav|//header|//footer|//pre'):
        node.drop_tree()
    roots = document.xpath('//main') or document.xpath('//article') or [document]
    blocks = []
    for node in roots[0].xpath('.//p|.//li[not(.//p) and not(.//li)]'):
        text = ' '.join(node.text_content().split())
        if 25 <= len(text) <= 1400 and text not in blocks:
            blocks.append(text)
    terms = set(re.findall(r'\w{2,}', query.lower()))
    if require_match and not any(term in block.lower() for block in blocks for term in terms):
        raise ValueError('page contains no matching passage for the requested keywords')
    parent = local_path.replace('\\', '/').rsplit('/', 1)[0] if '/' in local_path or '\\' in local_path else ''
    context = set(re.findall(r'[^\W_]{4,}', parent.lower()))
    def score(index):
        text = blocks[index].lower()
        compact = ''.join(c for c in text if c.isalnum())
        return (sum(term in compact for term in context), sum(term in text for term in terms), -index)
    selected, size = [], 0
    if blocks:
        best = max(range(len(blocks)), key=score)
        # Keep the explanation and its nearby steps/conditions together instead of repeating scattered comments.
        for index in [best, best + 1, best + 2, best - 1]:
            if not 0 <= index < len(blocks):
                continue
            text = blocks[index]
            length = len(text.encode('utf-8'))
            if size + length <= 1800:
                selected.append((index, text))
                size += length
    content = '\n'.join(text for _, text in sorted(selected))
    if not content:
        raise ValueError('no readable article paragraphs')
    return content


def read(row, query, local_path="", require_match=False):
    result = dict(row)
    try:
        result.update(content=excerpt(fetch(row['url']), query, local_path, require_match), kind='web_document')
    except Exception as exc:
        result['read_error'] = str(exc)
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    data = json.loads(sys.argv[1])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        print(json.dumps({'results': list(pool.map(lambda row: read(row, data['query'], data.get('local_path', ''), data.get('find', False)), data['results'][:2]))}, ensure_ascii=False))
