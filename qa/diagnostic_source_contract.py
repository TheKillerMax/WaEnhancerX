"""Shared source lexer for reviewed Java/Kotlin diagnostic contracts.

Deliberately narrow source syntax; not an AST, taint or runtime privacy proof.
Extracted without behavior changes from the reviewed privacy-gate implementation.
"""
from dataclasses import dataclass
import re


class GateFailure(AssertionError):
    """Explicit checks stay active when imported by optimized Python tests."""


def require(condition, message):
    if not condition:
        raise GateFailure(message)


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    quoted: bool = False


def tokens(source, kotlin=False):
    """Small lexer for reviewed call syntax, not a Java/Kotlin compiler.

    Ignore comments, preserve literals, and handle nested Kotlin interpolations.
    Java Unicode preprocessing is deliberately unsupported and rejected rather
    than allowing escaped identifiers/comments to evade this source gate.
    """
    if not kotlin and re.search(r'\\u+[0-9a-fA-F]{4}', source):
        raise GateFailure('Java Unicode escapes require explicit lexer review')

    def comment_end(at):
        if source.startswith('//', at):
            end = source.find('\n', at + 2)
            return len(source) if end < 0 else end
        depth, pos = 1, at + 2
        while pos < len(source):
            if kotlin and source.startswith('/*', pos):
                depth += 1
                pos += 2
            elif source.startswith('*/', pos):
                depth -= 1
                pos += 2
                if not depth:
                    return pos
            else:
                pos += 1
        raise GateFailure('Unterminated block comment')

    def interpolation_end(at):
        depth, pos = 1, at
        while pos < len(source):
            if source.startswith(('//', '/*'), pos):
                pos = comment_end(pos)
            elif source[pos] in '\"\'':
                pos = quoted_end(pos)
            elif source[pos] == '{':
                depth += 1
                pos += 1
            elif source[pos] == '}':
                depth -= 1
                pos += 1
                if not depth:
                    return pos
            else:
                pos += 1
        raise GateFailure('Unterminated Kotlin interpolation')

    def quoted_end(at):
        quote = source[at]
        triple = quote == '"' and source.startswith('"""', at)
        delimiter = '"""' if triple else quote
        pos = at + len(delimiter)
        while pos < len(source):
            if source.startswith(delimiter, pos):
                return pos + len(delimiter)
            if not triple and source[pos] == '\\':
                pos += 2
            elif kotlin and quote == '"' and source.startswith('${', pos):
                begin = pos + 2
                pos = interpolation_end(begin)
                inner = tokens(source[begin:pos - 1], kotlin=True)
                if any(not token.quoted and token.value == 'XposedBridge' for token in inner):
                    raise GateFailure('Xposed references inside Kotlin interpolation require AST review')
            else:
                pos += 1
        raise GateFailure('Unterminated string/character literal')

    out, pos = [], 0
    while pos < len(source):
        start = pos
        if source[pos].isspace():
            pos += 1
        elif source.startswith(('//', '/*'), pos):
            pos = comment_end(pos)
        elif source[pos] in '\"\'':
            pos = quoted_end(pos)
            value = source[start:pos]
            out.append(Token(value, start, pos, True))
        elif source[pos] == '`':
            raise GateFailure('Backtick identifiers require explicit lexer review')
        elif source[pos].isalpha() or source[pos] in '_$':
            pos += 1
            while pos < len(source) and (source[pos].isalnum() or source[pos] in '_$'):
                pos += 1
            out.append(Token(source[start:pos], start, pos))
        else:
            pos += 1
            out.append(Token(source[start:pos], start, pos))
    return out


def signature(source, kotlin=False):
    return tuple(token.value for token in tokens(source, kotlin))


def log_calls(source, kotlin=False):
    lexed = tokens(source, kotlin)
    values = [token.value for token in lexed]
    for index, token in enumerate(lexed):
        if token.quoted or token.value != 'XposedBridge':
            continue
        tail = values[index + 1:index + 4]
        class_import = ['import', 'de', '.', 'robv', '.', 'android', '.', 'xposed', '.', 'XposedBridge']
        if values[max(0, index - 9):index + 1] == class_import:
            require(not tail or tail[0] not in ('.', 'as'), 'Only the unaliased XposedBridge class import is reviewed')
            continue
        # Fail closed on generic static calls, casts/typed aliases, class literals,
        # method references and imported log aliases. Otherwise an extra legal
        # Java call such as XposedBridge.<String>log(payload) could evade inventory.
        reviewed_members = {'log', 'hookMethod', 'hookAllMethods', 'hookAllConstructors'}
        require(len(tail) == 3 and tail[0] == '.' and tail[1] in reviewed_members and tail[2] == '(',
                'Only reviewed direct XposedBridge calls are supported; other references require review')
        if tail[1] != 'log':
            continue
        depth = 1
        for end in range(index + 4, len(lexed)):
            value = lexed[end].value
            if value == '(':
                depth += 1
            elif value == ')':
                depth -= 1
                if not depth:
                    start_at, end_at = lexed[index + 3].end, lexed[end].start
                    yield source.count('\n', 0, token.start) + 1, source[start_at:end_at]
                    break
        else:
            raise GateFailure('Unbalanced XposedBridge.log call')


def hook_logs(source):
    """Compatibility adapter for the existing Java delimiter fixture suite."""
    return (expression for _, expression in log_calls(source))


DYNAMIC_PII = re.compile(
    r'(?:\+\s*|\$\{\s*|\$(?!\{))'
    r'(?:keyId|key|jid|chatJid|senderJid|senderName|senderDisplayName|'
    r'chatDisplayName|textData|messageText|newMessage|phoneNumber|rawJid)\b')
RAW_EXCEPTION_TEXT = re.compile(
    r'\.\s*(?:getMessage|getLocalizedMessage)\s*\('
    r'|\$\{[^}]*\.\s*(?:message|localizedMessage)\s*\}')
RAW_EXCEPTION_OBJECT = re.compile(
    r'\$\{\s*(?:t|ex|e|error|throwable)\s*\}|\$(?:t|ex|e|error|throwable)\b'
    r'|\+\s*(?:t|ex|e|error|throwable)(?![\w.])'
    r'|\+\s*(?:t|ex|e|error|throwable)\.toString\s*\(')
RAW_LITERAL = re.compile(r'(?:keyId|message[_ -]?id|sender[_ -]?jid|chat[_ -]?jid)\s*=')


def exposure(expression):
    return any(regex.search(expression) for regex in
               (DYNAMIC_PII, RAW_EXCEPTION_TEXT, RAW_EXCEPTION_OBJECT, RAW_LITERAL))


def fragment(source, text, kotlin=False):
    haystack, needle = signature(source, kotlin), signature(text, kotlin)
    return any(haystack[i:i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


def block(source, declaration):
    """Extract one braced body by tokens; comments cannot impersonate a guard."""
    lexed, needle = tokens(source), signature(declaration)
    values = [token.value for token in lexed]
    matches = [i + len(needle) for i in range(len(values) - len(needle))
               if tuple(values[i:i + len(needle)]) == needle and values[i + len(needle)] == '{']
    require(len(matches) == 1, 'Expected one block: ' + declaration)
    at, depth = matches[0], 1
    for end in range(at + 1, len(values)):
        if values[end] == '{':
            depth += 1
        elif values[end] == '}':
            depth -= 1
            if not depth:
                return source[lexed[at].end:lexed[end].start]
    raise GateFailure('Unclosed block: ' + declaration)
