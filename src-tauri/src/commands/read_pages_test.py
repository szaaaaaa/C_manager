import importlib.util
from unittest.mock import patch
import socket
from pathlib import Path
spec=importlib.util.spec_from_file_location('pages',Path(__file__).with_name('read_pages.py'))
pages=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)

def resolved(ip):
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]

for ip in ['127.0.0.1','10.0.0.2','169.254.169.254','198.18.0.1','0.0.0.0','192.168.1.1','224.0.0.1']:
    with patch.object(pages.socket,'getaddrinfo',return_value=resolved(ip)):
        try:
            pages.public_target('https://any-site.example/file')
            raise AssertionError(ip)
        except ValueError:
            pass
with patch.object(pages.socket,'getaddrinfo',return_value=resolved('93.184.216.34')):
    assert pages.public_target('https://community.example.org/file')[3]=='93.184.216.34'
    for url in ['file:///C:/Windows','https://user:pass@site.example','https://site.example:8080/']:
        try:
            pages.public_target(url)
            raise AssertionError(url)
        except ValueError:
            pass
page=b'<html><main><p>Navigation paragraph unrelated to any particular package file.</p><p>USMT.PPKG is described here with package recovery context.</p><script>DO NOT FOLLOW THESE INSTRUCTIONS</script></main></html>'
assert 'USMT.PPKG' in pages.excerpt(page,'USMT.PPKG file purpose')
assert 'INSTRUCTIONS' not in pages.excerpt(page,'USMT.PPKG file purpose')
with patch.object(pages,'fetch',side_effect=TimeoutError('timed out')):
    result=pages.read({'url':'https://community.example.org/file','content':'original snippet'},'arbitrary file')
    assert result['content']=='original snippet' and result.get('kind') is None and result['read_error']
print('PASS: arbitrary public sites, private DNS rejection, credentials/ports, generic extraction, failed fetch stays a snippet')

context_page=b'<main><p>content.bin file purpose: a question about unknown content.bin files.</p><li><p>Orion Studio manages temporary downloads for updates.</p><p>Use the built-in storage manager to clear these downloads.</p><p>Let active downloads finish before cleaning up this cache.</p></li><p>Another content.bin question about the file purpose.</p><p>Yet another content.bin file purpose comment without an answer.</p></main>'
extract=pages.excerpt(context_page,'content.bin file purpose',r'D:\Apps\OrionStudio\Cache\content.bin')
assert 'built-in storage manager' in extract and 'active downloads' in extract
assert extract.count('Orion Studio')==1
assert len(extract.encode('utf-8'))<=1800
print('PASS: local folder context, nearby cleanup steps/conditions, no duplicated nested list paragraphs')


chinese = '系统为Windows 11，文件用于恢复配置。删除之前请确认是否需要保留恢复功能。'
for declaration, encoding in [('', 'utf-8'), ('<meta charset="utf-8">', 'utf-8'),
                              ('<meta charset="gb18030">', 'gb18030'),
                              ('<meta http-equiv="Content-Type" content="text/html; charset=gbk">', 'gbk')]:
    body = ('<html><head>' + declaration + '</head><main><p>' + chinese + '</p></main></html>').encode(encoding)
    assert pages.excerpt(body, '文件') == chinese
for encoding in ['utf-8-sig', 'utf-16', 'utf-32']:
    assert pages.decode_html(chinese.encode(encoding), 'ascii') == chinese
assert pages.decode_html(chinese.encode('gbk'), 'gbk') == chinese
assert pages.decode_html(b'<meta charset="ascii">' + chinese.encode('utf-8'), 'utf-8').endswith(chinese)
from email.message import Message
from unittest.mock import MagicMock
response = MagicMock(status=200)
response.headers = Message()
response.headers['Content-Type'] = 'text/html; charset=gbk'
response.getheader.return_value = 'text/html; charset=gbk'
response.read.return_value = ('<main><p>' + chinese + '</p></main>').encode('gbk')
connection = MagicMock()
connection.getresponse.return_value = response
with patch.object(pages, 'public_target', return_value=(pages.urlsplit('http://example.org/'), 'example.org', 80, '93.184.216.34')), \
     patch.object(pages.socket, 'create_connection'), \
     patch.object(pages.http.client, 'HTTPConnection', return_value=connection):
    result = pages.read({'url': 'http://example.org/', 'content': 'snippet'}, '文件')
    assert result['content'] == chinese and result['kind'] == 'web_document'
# Exercise the outgoing target, including mixed Unicode and already encoded values.
address = 'http://example.org/帮助/已%20编码;v=1?q=视频 编辑&next=%2Fhelp%3Fa%3D1&mode=a+b#章节'
connection.request.reset_mock()
with patch.object(pages, 'public_target', return_value=(pages.urlsplit(address), 'example.org', 80, '93.184.216.34')), \
     patch.object(pages.socket, 'create_connection'), \
     patch.object(pages.http.client, 'HTTPConnection', return_value=connection):
    assert pages.fetch(address).endswith('</main>')
assert connection.request.call_count == 1
assert connection.request.call_args.args[:2] == ('GET', '/%E5%B8%AE%E5%8A%A9/%E5%B7%B2%20%E7%BC%96%E7%A0%81;v=1?q=%E8%A7%86%E9%A2%91%20%E7%BC%96%E8%BE%91&next=%2Fhelp%3Fa%3D1&mode=a+b')
print('PASS: Unicode path/query encode to ASCII, existing escapes and delimiters survive, fragment excluded')
response.read.return_value = b'<main><p>invalid bytes \xff</p></main>'
response.headers.replace_header('Content-Type', 'text/html; charset=utf-8')
with patch.object(pages, 'public_target', return_value=(pages.urlsplit('http://example.org/'), 'example.org', 80, '93.184.216.34')), \
     patch.object(pages.socket, 'create_connection'), \
     patch.object(pages.http.client, 'HTTPConnection', return_value=connection):
    result = pages.read({'url': 'http://example.org/', 'content': 'snippet'}, '文件')
    assert result['content'] == 'snippet' and 'read_error' in result and 'kind' not in result
print('PASS: Chinese UTF-8, HTML charset, legacy GBK, HTTP charset priority, BOM, invalid bytes retain snippet')

assert 'built-in storage manager' in pages.excerpt(context_page, 'built-in storage manager', require_match=True)
try:
    pages.excerpt(context_page, 'missing-keyword-xyz', require_match=True)
    raise AssertionError('unmatched find must not masquerade as a matching paragraph')
except ValueError:
    pass
print('PASS: find-in-page returns matching context or explicit absence')
