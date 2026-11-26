"""Bounded, read-only APT source/index observation for the disposable lab runner.

No package commands, environment reads, authentication files, repository edits,
index contents or raw source lines are used. This supplies diagnostic evidence;
it never substitutes for the existing authenticated package/version/hash gate.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlsplit

LABELS = frozenset(('before_libpulse', 'after_apt_update'))
MAX_SOURCE_FILE_BYTES = 65536
MAX_TOTAL_SOURCE_BYTES = 524288
MAX_SOURCE_DIRECTORY_ENTRIES = 128
MAX_SOURCE_FILES = 64
MAX_STANZAS_PER_FILE = 32
MAX_SOURCE_ENTRIES = 128
MAX_INDEX_ENTRIES = 512
SOFT_BUDGET_SECONDS = 3.0
_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_KNOWN_FILES = frozenset(('sources.list', 'ubuntu.sources', 'microsoft-prod.list',
                          'microsoft-prod.sources', 'microsoft-edge.list'))
_SUITES = frozenset(('noble', 'noble-updates', 'noble-security', 'noble-backports',
                     'jammy', 'jammy-updates', 'jammy-security', 'jammy-backports',
                     'focal', 'focal-updates', 'focal-security', 'focal-backports', 'stable'))
_COMPONENTS = frozenset(('main', 'universe', 'restricted', 'multiverse'))
_ARCHITECTURES = frozenset(('amd64', 'arm64', 'i386', 'armhf', 'all'))


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _stat(info):
    return {'bytes': info.st_size, 'uid': info.st_uid, 'gid': info.st_gid,
            'mode': oct(stat.S_IMODE(info.st_mode)), 'device': info.st_dev,
            'inode': info.st_ino, 'links': info.st_nlink,
            'mtime_ns': info.st_mtime_ns}


def _error(exc):
    # Exception strings may include filenames or other private source data.
    return {'exception_class': type(exc).__name__, 'errno': getattr(exc, 'errno', None)}


def _tokens(value, allowed):
    values = value.replace(',', ' ').split()
    return {'known': sorted(set(values) & allowed),
            'other_count': sum(item not in allowed for item in values)}


def _key_kind(value):
    if not value:
        return 'not_explicit_in_source'
    if value == '/usr/share/keyrings/ubuntu-archive-keyring.gpg':
        return 'ubuntu_archive_keyring'
    if value in ('/usr/share/keyrings/microsoft-prod.gpg',
                 '/usr/share/keyrings/microsoft.gpg'):
        return 'microsoft_keyring'
    return 'other_configured_value_redacted'


def _uri(raw):
    result = {'userinfo_redacted': False, 'query_redacted': '?' in raw,
              'fragment_redacted': '#' in raw}
    try:
        if len(raw) > 2048 or '\x00' in raw:
            raise ValueError('URI bound')
        parts = urlsplit(raw)
        result['userinfo_redacted'] = '@' in parts.netloc
        host = (parts.hostname or '').lower()
        scheme = parts.scheme.lower()
        public_hostname = re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host) is not None
        if public_hostname and scheme in ('http', 'https') and (
                host in ('archive.ubuntu.com', 'security.ubuntu.com',
                         'ports.ubuntu.com', 'old-releases.ubuntu.com')
                or host.endswith('.archive.ubuntu.com')):
            result.update(provider='ubuntu', scheme=scheme, public_host=host,
                          path='/ubuntu' if parts.path.rstrip('/') == '/ubuntu' else '<redacted-other-path>')
        elif scheme in ('http', 'https') and host == 'packages.microsoft.com':
            path = parts.path.rstrip('/')
            result.update(provider='microsoft', scheme=scheme, public_host=host,
                          path=path if re.fullmatch(r'/ubuntu/\d{2}\.\d{2}/prod', path) else '<redacted-other-path>')
        elif scheme in ('mirror+file', 'file') and not parts.netloc:
            result.update(provider='local_mirror_source', scheme=scheme,
                          path='/etc/apt/apt-mirrors.txt' if parts.path == '/etc/apt/apt-mirrors.txt'
                          else '<redacted-other-path>')
        else:
            result.update(provider='other_redacted', scheme=scheme if scheme in ('http','https','file','mirror+file') else 'other')
    except (ValueError, UnicodeError):
        result.update(provider='unparseable_redacted', scheme='unknown')
    # Never emit the original URI, netloc, userinfo, port, query or fragment.
    return result


def _entry(fields, enabled, ordinal):
    uri_tokens = fields.get('uris', '').split()
    return {'ordinal': ordinal, 'enabled': enabled,
            'types': _tokens(fields.get('types', ''), frozenset(('deb','deb-src'))),
            'uris': [_uri(value) for value in uri_tokens[:8]],
            'uri_count_over_bound': max(0, len(uri_tokens)-8),
            'suites': _tokens(fields.get('suites', ''), _SUITES),
            'components': _tokens(fields.get('components', ''), _COMPONENTS),
            'architectures': _tokens(fields.get('architectures', ''), _ARCHITECTURES),
            'signed_by': _key_kind(fields.get('signed-by', '')),
            'trusted_option': fields.get('trusted') if fields.get('trusted') in ('yes','no')
                              else ('not_set' if 'trusted' not in fields else 'other_value_redacted')}


def _parse_list(text):
    rows, malformed, truncated = [], 0, False
    for line in text.splitlines():
        logical = line.strip()
        enabled = True
        if logical.startswith('#'):
            logical, enabled = logical[1:].lstrip(), False
        if not re.match(r'deb(?:-src)?\s', logical):
            continue
        if len(rows) >= MAX_STANZAS_PER_FILE:
            truncated = True
            break
        match = re.fullmatch(r'(deb(?:-src)?)\s+(?:\[([^\]]*)\]\s+)?(\S+)\s+(.+)', logical)
        if match is None:
            malformed += 1
            continue
        kind, option_text, uri, tail = match.groups()
        words = tail.split('#', 1)[0].split()
        if not words:
            malformed += 1
            continue
        options, duplicate_option = {}, False
        for option in (option_text or '').split():
            key, separator, value = option.partition('=')
            if separator and key in ('arch','signed-by','trusted'):
                duplicate_option |= key in options
                options[key] = value
        if duplicate_option:
            malformed += 1
            continue
        fields = {'types':kind, 'uris':uri, 'suites':words[0], 'components':' '.join(words[1:]),
                  'architectures':options.get('arch',''), 'signed-by':options.get('signed-by','')}
        if 'trusted' in options:
            fields['trusted'] = options['trusted']
        rows.append(_entry(fields, enabled, len(rows)+1))
    return {'entries':rows, 'malformed_count':malformed, 'truncated':truncated}


def _parse_sources(text):
    rows, malformed, truncated = [], 0, False
    paragraphs = re.split(r'\n\s*\n', text)
    for paragraph in paragraphs:
        if not paragraph.strip():
            continue
        fields, duplicates, previous = {}, set(), None
        for line in paragraph.splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if line[0].isspace() and previous is not None:
                fields[previous] += ' '+line.strip()
                continue
            key, separator, value = line.partition(':')
            key = key.strip().lower()
            if not separator or not re.fullmatch('[a-z][a-z-]*', key):
                duplicates.add('malformed_line')
                previous = None
                continue
            if key in fields:
                duplicates.add('duplicate_field')
            fields[key], previous = value.strip(), key
        if not fields and not duplicates:
            continue
        if len(rows) >= MAX_STANZAS_PER_FILE:
            truncated = True
            break
        if duplicates or not all(fields.get(name) for name in ('types','uris','suites')):
            malformed += 1
            continue
        enabled_value = fields.get('enabled','yes').lower()
        enabled = True if enabled_value == 'yes' else False if enabled_value == 'no' else None
        rows.append(_entry(fields, enabled, len(rows)+1))
    return {'entries':rows, 'malformed_count':malformed, 'truncated':truncated}


def _source_file(directory_fd, name, display, remaining):
    row = {'file':display, 'name_sha256':_digest(os.fsencode(name)), 'status':'UNREAD'}
    fd = None
    try:
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        row['stat'] = _stat(before)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            row['status'] = 'SKIPPED_NONREGULAR_OR_MULTILINK'
            return row, 0
        if not 0 <= before.st_size <= min(MAX_SOURCE_FILE_BYTES, remaining):
            row['status'] = 'SKIPPED_BYTE_BOUND'
            return row, 0
        fd = os.open(name, _FLAGS, dir_fd=directory_fd)
        opened = os.fstat(fd)
        if _stat(opened) != _stat(before) or not stat.S_ISREG(opened.st_mode):
            row['status'] = 'SKIPPED_CHANGED_BEFORE_READ'
            return row, 0
        # The extra byte detects growth unless already at a strict byte cap;
        # fstat detects changed size in either case. Never read over either cap.
        raw = os.read(fd, min(before.st_size+1, MAX_SOURCE_FILE_BYTES, remaining))
        if len(raw) != before.st_size or _stat(os.fstat(fd)) != _stat(before):
            row['status'] = 'SKIPPED_CHANGED_DURING_READ'
            return row, len(raw)
        row['content_sha256'] = _digest(raw)
        text = raw.decode('utf8', errors='strict')
        parsed = _parse_sources(text) if name.endswith('.sources') else _parse_list(text)
        row.update(status='READ_SANITIZED', format='deb822' if name.endswith('.sources') else 'one_line', **parsed)
        return row, len(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        row.update(status='UNAVAILABLE_OR_INVALID', error=_error(exc))
        return row, 0 if fd is None else before.st_size
    finally:
        if fd is not None:
            os.close(fd)


def _names(fd, limit):
    names = []
    with os.scandir(fd) as iterator:
        for entry in iterator:
            if len(names) == limit:
                return sorted(names), True
            names.append(entry.name)
    return sorted(names), False


def _index_hints(name):
    # Filename hints are not authenticated repository identities or package contents.
    hints = {'provider_hint':'other_or_unknown'}
    if name.startswith('packages.microsoft.com_'):
        hints['provider_hint'] = 'microsoft'
    elif re.match(r'(?:[a-z0-9.-]+\.)?(?:archive|security|ports|old-releases)\.ubuntu\.com_', name):
        hints['provider_hint'] = 'ubuntu'
    elif name.startswith('mirror+file:_etc_apt_apt-mirrors.txt_'):
        hints['provider_hint'] = 'local_mirror_list'
    hints['suite_hints'] = [suite for suite in sorted(_SUITES) if '_'+suite+'_' in name]
    hints['component_hints'] = [c for c in sorted(_COMPONENTS) if '_'+c+'_' in name]
    hints['architecture_hints'] = [a for a in sorted(_ARCHITECTURES) if '_binary-'+a+'_' in name]
    match = re.search(r'_(InRelease|Release|Release\.gpg|Packages|Sources|Translation-en)(?:\.(?:lz4|gz|xz|bz2))?$', name)
    hints['index_type_hint'] = match[1] if match else 'other_or_unknown'
    return hints


def _snapshot_paths(label, apt_root, lists_root):
    if label not in LABELS:
        raise ValueError('Unexpected APT observation label')
    started = time.monotonic()
    result = {'schema':'WAEX_APT_SOURCE_INDEX_OBSERVATION_V1', 'label':label, 'status':'OBSERVED',
              'read_only':True, 'source_files':[], 'index_entries':[], 'errors':[], 'truncated':False,
              'source_bytes_read':0, 'auth_files_read':False, 'environment_read':False,
              'index_contents_read':False, 'raw_source_lines_retained':False,
              'scope':'Fixed source files only; index stat only; no repository/configuration changes or commands.',
              'limits':{'source_file_bytes':MAX_SOURCE_FILE_BYTES, 'total_source_bytes':MAX_TOTAL_SOURCE_BYTES,
                        'source_directory_entries':MAX_SOURCE_DIRECTORY_ENTRIES, 'source_files':MAX_SOURCE_FILES,
                        'stanzas_per_file':MAX_STANZAS_PER_FILE, 'source_entries':MAX_SOURCE_ENTRIES,
                        'index_entries':MAX_INDEX_ENTRIES,
                        'soft_budget_seconds':SOFT_BUDGET_SECONDS, 'hard_deadline_claimed':False}}
    def budget():
        ok = time.monotonic()-started <= SOFT_BUDGET_SECONDS
        if not ok:
            result['truncated'] = True
        return ok
    def append_source(row, count):
        already = sum(len(r.get('entries', [])) for r in result['source_files'])
        available = max(0, MAX_SOURCE_ENTRIES-already)
        if len(row.get('entries', [])) > available:
            row['entries_omitted_by_global_bound'] = len(row['entries'])-available
            row['entries'] = row['entries'][:available]
            row['truncated'] = True
        result['source_files'].append(row)
        result['source_bytes_read'] += count
        result['truncated'] |= row.get('truncated',False)
    apt_fd = sources_fd = lists_fd = None
    try:
        try:
            apt_fd = os.open(apt_root, _FLAGS | os.O_DIRECTORY)
            row, count = _source_file(apt_fd, 'sources.list', 'sources.list', MAX_TOTAL_SOURCE_BYTES)
            append_source(row, count)
            sources_fd = os.open('sources.list.d', _FLAGS | os.O_DIRECTORY, dir_fd=apt_fd)
            names, truncated = _names(sources_fd, MAX_SOURCE_DIRECTORY_ENTRIES)
            result['truncated'] |= truncated
            result['source_directory_entries_retained'] = len(names)
            for name in names:
                if not (name.endswith('.list') or name.endswith('.sources')):
                    continue
                if len(result['source_files']) >= MAX_SOURCE_FILES or not budget():
                    result['truncated'] = True
                    break
                display = name if name in _KNOWN_FILES else '<other-source-file>'
                row, count = _source_file(sources_fd, name, display, MAX_TOTAL_SOURCE_BYTES-result['source_bytes_read'])
                append_source(row, count)
        except (OSError, ValueError) as exc:
            result['errors'].append({'scope':'sources', **_error(exc)})
        if budget():
            try:
                lists_fd = os.open(lists_root, _FLAGS | os.O_DIRECTORY)
                names, truncated = _names(lists_fd, MAX_INDEX_ENTRIES)
                result['truncated'] |= truncated
                for name in names:
                    if not budget():
                        break
                    row = {'name_sha256':_digest(os.fsencode(name)), **_index_hints(name)}
                    try:
                        info = os.stat(name, dir_fd=lists_fd, follow_symlinks=False)
                        row.update(stat=_stat(info), type='regular' if stat.S_ISREG(info.st_mode)
                                   else 'directory' if stat.S_ISDIR(info.st_mode)
                                   else 'symlink' if stat.S_ISLNK(info.st_mode) else 'other')
                    except OSError as exc:
                        row['error'] = _error(exc)
                    result['index_entries'].append(row)
                result['index_entries'].sort(key=lambda row:row['name_sha256'])
            except (OSError, ValueError) as exc:
                result['errors'].append({'scope':'index_stat', **_error(exc)})
    finally:
        for fd in (lists_fd,sources_fd,apt_fd):
            if fd is not None:
                os.close(fd)
    if result['truncated'] or result['errors'] or any(
            row['status'] != 'READ_SANITIZED' or row.get('malformed_count',0)
            for row in result['source_files']):
        result['status'] = 'PARTIAL_OBSERVATION'
    result['elapsed_seconds'] = round(time.monotonic()-started, 6)
    return result


def snapshot(label):
    """Return bounded sanitized metadata for the fixed APT paths; do not write."""
    return _snapshot_paths(label, Path('/etc/apt'), Path('/var/lib/apt/lists'))
