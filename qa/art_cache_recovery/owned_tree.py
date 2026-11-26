"""Bounded ownership and cleanup of one new shell-UID lab tree; no transport here."""
import hashlib
import json
import re
import shlex
import stat


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


class OwnedTree:
    """Callbacks preserve command/raw-file evidence; unknown entries are never removed.

    The caller owns a fresh isolated AVD and must reap it after any exception.
    This protocol detects observed path changes; it does not claim atomic protection
    against a hostile concurrent process with the same shell UID.
    """
    PREFIXES = ('waex-art-cache-probe', 'waex-art-recovery')
    MARKER = 'ownership.json'
    MAX_FILE = 4 * 1024 * 1024
    MAX_TOTAL = 16 * 1024 * 1024
    MAX_ENTRIES = 12

    def __init__(self, *, command, read_file, read_boot, nonce, boot, prefix, inputs, producer):
        require(re.fullmatch(r'[0-9a-f]{32}', nonce) is not None, 'Invalid tree nonce')
        require(re.fullmatch(r'[0-9a-f-]{36}', boot) is not None, 'Invalid pinned boot')
        require(prefix in self.PREFIXES, 'Tree prefix is not a new recovery scope')
        require(isinstance(inputs, dict) and 1 <= len(inputs) <= 3, 'One to three explicit JAR inputs required')
        for name, pin in inputs.items():
            require(re.fullmatch(r'[a-z][a-z0-9_-]{0,31}\.jar', name) is not None,
                    'Input name is not a fixed simple JAR name')
            require(set(pin) == {'bytes', 'sha256'} and type(pin['bytes']) is int
                    and 0 < pin['bytes'] <= self.MAX_FILE
                    and re.fullmatch(r'[0-9a-f]{64}', pin['sha256']) is not None, 'Invalid input pin')
        self.command, self.read_file, self.read_boot = command, read_file, read_boot
        self.nonce, self.boot, self.inputs = nonce, boot, dict(inputs)
        self.path = '/data/local/tmp/' + prefix + '-' + nonce
        self.marker = (json.dumps({'schema': 'WAEX_OWNED_ART_TREE_V1', 'nonce': nonce,
                                  'boot_id': boot, 'path': self.path, 'inputs': inputs,
                                  'producer': producer}, sort_keys=True, separators=(',', ':')) + '\n').encode()
        require(len(self.marker) <= 4096, 'Ownership marker exceeds its bound')
        self.marker_pin = {'bytes': len(self.marker), 'sha256': hashlib.sha256(self.marker).hexdigest()}
        self.root_identity = None
        self.marker_identity = None
        self.sequence = 0
        self.events = []

    def _name(self, suffix):
        self.sequence += 1
        return 'tree-%03d-%s' % (self.sequence, suffix)

    def _run(self, suffix, script):
        value = self.command(self._name(suffix), script, timeout=10)
        require(isinstance(value, str) and len(value.encode('utf-8')) <= 65536,
                'Tree command exceeded its text bound')
        value = value.replace('\r\n', '\n')
        require('\r' not in value and '\x00' not in value, 'Unexpected tree command encoding')
        return value

    def _path(self, rel):
        require(rel in self._allowed(), 'Unapproved relative tree path')
        return self.path + '/' + rel

    def _allowed(self):
        result = {self.MARKER: 'file', **{n: 'file' for n in self.inputs},
                  'oat': 'directory', 'oat/x86_64': 'directory'}
        for name in self.inputs:
            for ext in ('.odex', '.vdex'):
                result['oat/x86_64/' + name[:-4] + ext] = 'file'
        return result

    def _stat(self, path):
        quoted = shlex.quote(path)
        raw = self._run('lstat',
                        'if [ -L ' + quoted + ' ]; then printf "LINK\\n"; '
                        'elif [ ! -e ' + quoted + ' ]; then printf "ABSENT\\n"; '
                        "else stat -c '%f|%u|%g|%d|%i|%h|%s|%Y|%Z' -- " + quoted + '; fi')
        if raw == 'ABSENT\n':
            return None
        require(raw != 'LINK\n', 'A tree path is a symlink: ' + path)
        match = re.fullmatch(r'([0-9a-fA-F]{1,8})\|([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9]+)\n', raw)
        require(match is not None, 'Unsupported or ambiguous lstat output')
        values = [int(match[1], 16)] + [int(match[i]) for i in range(2, 10)]
        require(all(0 <= v <= (1 << 64) - 1 for v in values), 'Stat value out of range')
        result = dict(zip(('mode', 'uid', 'gid', 'device', 'inode', 'nlink', 'bytes', 'mtime', 'ctime'), values))
        require(result['uid'] == 2000 and result['gid'] == 2000 and result['inode'] > 0,
                'Tree ownership is not the shell UID/GID')
        require(stat.S_ISREG(result['mode']) or stat.S_ISDIR(result['mode']), 'Tree path has a forbidden type')
        if stat.S_ISREG(result['mode']):
            require(result['nlink'] == 1, 'Hardlinked tree file rejected')
            require(stat.S_IMODE(result['mode']) in (0o400, 0o444, 0o600, 0o640, 0o644),
                    'Unexpected tree file permissions')
        else:
            require(stat.S_IMODE(result['mode']) in (0o700, 0o711), 'Unexpected tree directory permissions')
        return result

    @staticmethod
    def _identity(row):
        return {k: row[k] for k in ('mode', 'uid', 'gid', 'device', 'inode')}

    def _boot_uid(self):
        require(self.read_boot() == self.boot, 'Boot changed before tree operation')
        require(self._run('uid', 'id -u') == '2000\n', 'Tree command is not shell UID2000')

    def _root(self, *, check_marker=True):
        require(self.root_identity is not None, 'Tree has no confirmed creation identity')
        self._boot_uid()
        row = self._stat(self.path)
        require(row is not None and self._identity(row) == self.root_identity,
                'Owned root identity changed')
        if check_marker:
            marker = self._stat(self._path(self.MARKER))
            require(marker is not None and self.marker_identity is not None
                    and self._identity(marker) == self.marker_identity, 'Ownership marker identity changed')
            self._file(self.MARKER, marker, self.marker_pin)
        return row

    def _file(self, rel, metadata, pin=None):
        require(stat.S_ISREG(metadata['mode']) and 0 <= metadata['bytes'] <= self.MAX_FILE,
                'File type or byte bound differs: ' + rel)
        raw = self.read_file(self._name('readback'), self._path(rel), metadata['bytes'])
        require(isinstance(raw, bytes) and len(raw) == metadata['bytes'], 'File transfer length differs: ' + rel)
        require(self._stat(self._path(rel)) == metadata, 'File metadata changed during readback: ' + rel)
        actual = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if pin is not None:
            require(actual == pin, 'File hash/size differs: ' + rel)
        return {**metadata, 'sha256': actual['sha256']}

    def create(self):
        require(self.root_identity is None, 'Tree creation cannot be repeated')
        self._boot_uid()
        require(self._stat(self.path) is None, 'Tree path already exists')
        require(self._run('mkdir', 'umask 077; mkdir -m 700 -- ' + shlex.quote(self.path)) == '',
                'Unexpected mkdir output')
        root = self._stat(self.path)
        require(root is not None and stat.S_ISDIR(root['mode']) and stat.S_IMODE(root['mode']) == 0o700,
                'Created root identity is not an owned directory')
        self.root_identity = self._identity(root)
        marker_path = self._path(self.MARKER)
        require(self._stat(marker_path) is None, 'Ownership marker already exists')
        require(self._run('marker-create', '(umask 077; set -C; printf %s ' +
                         shlex.quote(self.marker.decode()) + ' > ' + shlex.quote(marker_path) + ')') == '',
                'Unexpected marker creation output')
        marker = self._stat(marker_path)
        require(marker is not None and stat.S_IMODE(marker['mode']) == 0o600,
                'Ownership marker mode differs')
        self.marker_identity = self._identity(marker)
        self._file(self.MARKER, marker, self.marker_pin)
        first = self.inventory()
        require(set(first['entries']) == {self.MARKER}, 'Created root is not initially exclusive')
        self.events.append({'event': 'created', 'root': self.root_identity, 'marker': self.marker_pin})
        return first

    def _children(self, rel):
        path = self.path if rel == '' else self._path(rel)
        raw = self._run('list', 'LC_ALL=C ls -A -1 -- ' + shlex.quote(path))
        if raw == '':
            return []
        require(raw.endswith('\n'), 'Directory listing is truncated')
        names = raw[:-1].split('\n')
        require(len(names) <= self.MAX_ENTRIES and len(names) == len(set(names)), 'Listing count or duplicates differ')
        require(all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', n) is not None
                    and n not in ('.', '..') for n in names), 'Unexpected directory-entry encoding/name')
        return sorted(names)

    def inventory(self, *, require_inputs=False):
        root = self._root()
        pending, entries, total = [''], {}, 0
        allowed = self._allowed()
        while pending:
            parent = pending.pop(0)
            if parent:
                require(self._stat(self._path(parent)) == entries[parent], 'Directory changed before traversal')
            for name in self._children(parent):
                rel = parent + '/' + name if parent else name
                require(rel in allowed and len(rel.split('/')) <= 3, 'Unknown descendant retained: ' + rel)
                require(rel not in entries and len(entries) < self.MAX_ENTRIES, 'Inventory size/duplication differs')
                row = self._stat(self._path(rel))
                require(row is not None and row['device'] == self.root_identity['device'], 'Descendant changed filesystem')
                if allowed[rel] == 'directory':
                    require(stat.S_ISDIR(row['mode']), 'Expected directory has another type')
                    entries[rel] = row
                    pending.append(rel)
                else:
                    pin = self.marker_pin if rel == self.MARKER else self.inputs.get(rel)
                    entries[rel] = self._file(rel, row, pin)
                    total += row['bytes']
                    require(total <= self.MAX_TOTAL, 'Inventory byte budget exceeded')
        require(self.MARKER in entries, 'Ownership marker missing from inventory')
        if require_inputs:
            require(set(self.inputs).issubset(entries), 'Pinned JAR inputs missing before launch')
        require(self._root() == root, 'Root changed while inventory was collected')
        result = {'root': root, 'entries': entries, 'total_regular_bytes': total}
        self.events.append({'event': 'inventory', 'sha256': hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
                            'entries': sorted(entries)})
        return result

    def clean(self):
        # Full admission precedes the first deletion, including every unexpected-path check.
        first = self.inventory()
        second = self.inventory()
        require(first == second, 'Inventory is unstable; nothing removed')
        entries = first['entries']
        removed = []
        cache_files = sorted(k for k, row in entries.items() if k.startswith('oat/') and stat.S_ISREG(row['mode']))
        input_files = sorted(k for k in self.inputs if k in entries)
        directories = sorted((k for k, row in entries.items() if stat.S_ISDIR(row['mode'])),
                             key=lambda k: (-len(k.split('/')), k))
        def remove_file(rel):
            self._root()
            row = self._stat(self._path(rel))
            require(row is not None and self._file(rel, row) == entries[rel], 'File changed before exact removal')
            require(self._run('remove-file', 'rm -- ' + shlex.quote(self._path(rel))) == '', 'Unexpected rm output')
            require(self._stat(self._path(rel)) is None, 'Removed file still exists')
            removed.append(rel)
        for rel in cache_files:
            remove_file(rel)
        for rel in directories:
            self._root()
            current = self._stat(self._path(rel))
            require(current is not None and self._identity(current) == self._identity(entries[rel]),
                    'Directory identity changed before rmdir')
            require(self._children(rel) == [], 'Directory gained unknown contents; retained')
            require(self._run('remove-directory', 'rmdir -- ' + shlex.quote(self._path(rel))) == '', 'Unexpected rmdir output')
            require(self._stat(self._path(rel)) is None, 'Removed directory still exists')
            removed.append(rel)
        for rel in input_files:
            remove_file(rel)
        require(self._children('') == [self.MARKER], 'Root gained unknown contents before marker removal')
        remove_file(self.MARKER)
        self._root(check_marker=False)
        require(self._children('') == [], 'Root is not empty after exact cleanup')
        require(self._run('remove-root', 'rmdir -- ' + shlex.quote(self.path)) == '', 'Unexpected root rmdir output')
        self._boot_uid()
        require(self._stat(self.path) is None, 'Root absence not verified')
        result = {'status': 'PASS', 'root_absent': True, 'removed': removed,
                  'inventory_before': first, 'cache_descendants': sorted(k for k in entries if k.startswith('oat')),
                  'recursive_deletion_used': False}
        self.events.append({'event': 'cleaned', 'root_absent': True})
        return result
