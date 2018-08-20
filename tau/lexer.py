import prompt_toolkit as ptk
import sys
import os
import re
import dtypes

# Pygments settings
example_style = ptk.styles.style_from_dict({
    ptk.token.Token.DefaultPrompt: '#8AE234 bold',
})


def _getContinuePrompt_(x):
    return [(ptk.token.Token.DefaultPrompt, "---> ")]


def _getTopLevelPrompt_(x):
    return [(ptk.token.Token.DefaultPrompt, "Tau> ")]


class InputBuffer():
    def __init__(self, source, quiet=False):
        self.source = source
        self.quiet = quiet
        self.buffer = []
        self.stringInput = isinstance(source, str)
        if self.stringInput:
            self.buffer = [line for line in source.splitlines() if line]
        self.REPLMode = source is sys.stdin
        if self.REPLMode:
            self.promptHistory = ptk.history.FileHistory(os.path.expanduser("~/.tauhistory"))

    def _fillBuffer_(self, level=0):
        if self.stringInput:
            raise EOFError
        while True:
            if self.REPLMode and sys.stdout.isatty() and not self.quiet:
                # Interactive session: Prompt for user input
                output = ptk.shortcuts.prompt(
                    history=self.promptHistory,
                    get_prompt_tokens=_getContinuePrompt_ if level > 0 else _getTopLevelPrompt_,
                    style=example_style,
                    default=u" "*4*level) + '\n'
            else:
                # Non-interactive session (File, piped input, etc)
                output = self.source.readline()
                if output == "":
                    # A blank line returns '\n', so this must be EOF
                    raise EOFError
            if output.strip() != "" or not ((self.REPLMode and level == 0) or not self.REPLMode):
                break
        self.buffer += output.splitlines()
        return

    def getLine(self, level=0):
        if not self.buffer:
            self._fillBuffer_(level)
        return self.buffer.pop(0)

    def peek(self, level=0):
        if not self.buffer:
            self._fillBuffer_(level)
        return self.buffer[0]

    def end(self, level=0):
        try:
            nextline = self.peek(level)
        except EOFError:
            return True
        # Blank lines in REPLMode indicate the end of all blocks
        if self.REPLMode and nextline.strip() == "":
            if level <= 1:
                self.getLine()
            return True
        # Check indentation level
        indentation = len(nextline.rstrip()) - len(nextline.strip())
        if indentation > level*4:
            raise ValueError("ERROR: Too much indentation, expected {} or less".format(level*4))
        elif indentation % 4 != 0:
            raise ValueError("Indentation must be a multiple of 4.")
        elif indentation < level*4:
            return True
        # Everything looks good: this isn't the end of the current block
        return False


class Token():
    precedence = ['print', '=', '+=', '-=', '/=', '//=', '*=', '**=', '%=', 'and', 'or',
                  'xor', '<=', '>=', '<', '>', '!=', '==',  '-', '+', '%', '*', '//', '/',
                  '**', 'unary +', 'unary -', 'indexing', 'function', 'free', 'array',
                  'literalArray', '()',  'literal', 'name', 'type']
    valueTokens = ['function', 'array', '()', 'indexing', 'literal', 'name', 'type',
                   'literalArray']

    def __init__(self, name, data=None):
        self.name = name
        self.data = data

    def getPrecedence(self):
        return Token.precedence.index(self.name)


def lex(code, debugLexer=False):
    tokens = []
    unprocessed = code.strip()
    while unprocessed:
        lastWasValue = tokens and tokens[-1].name in Token.valueTokens
        # Identify comments
        if unprocessed[0] == '#':
            break
        # Identify block-starting keywords
        match = re.match(r"(def|while|if)\b", unprocessed)
        if match:
            if tokens:
                raise ValueError("ERROR: Keyword {} must start the line.".format(match.group()))
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):-1].strip()
            continue
        # Identify for loop (currently only supports range(n))
        match = re.match(r"for\b", unprocessed)
        if match:
            if tokens:
                raise ValueError("ERROR: Keyword {} must start the line.".format(match.group()))
            unprocessed = unprocessed[len(match.group()):-1].strip()
            tokens.append(Token(match.group()))
            continue
        # Identify line-starting keywords
        match = re.match(r"(print|end)\b", unprocessed)
        if match:
            if tokens:
                raise ValueError("ERROR: Keyword {} must start the line.".format(match.group()))
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify other keywords
        match = re.match(r"(in|and|or|xor)\b", unprocessed)
        if match:
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            assertLastValue(tokens)
            continue
        # Identify possibly unary symbols
        match = re.match(r'(\+|-)(?!\*?/?=)', unprocessed)
        if match:
            if lastWasValue:  # Binary operator
                tokens.append(Token(match.group()))
            else:  # Unary operator
                tokens.append(Token("unary "+match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify basic symbols
        match = re.match(r'(,|\*\*?|%|//?|<=?|>=?|==)(?!\*?/?=)', unprocessed)
        if match:
            tokens.append(Token(match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            assertLastValue(tokens)
            continue
        # Identify assignment operation
        match = re.match(r'((\+|-|//?|\*\*?|%)?=)', unprocessed)
        if match:
            if len(tokens) == 1 and tokens[0].name == 'name':
                tokens.append(Token(match.group(), tokens.pop(0).data))
            elif len(tokens) > 1 and tokens[-1].name == "indexing":
                tokens, left = [], tokens
                tokens.append(Token(match.group(), left))
            else:
                raise ValueError("ERROR: Assignment must be immeditely follow variable name.")
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify parentheses and function calls and eat the contents
        if unprocessed.startswith("("):
            right = findMatching(unprocessed)
            if tokens and tokens[-1].name == "name":
                # This is a function call!
                caller = tokens.pop(-1).data
                if caller in ["free"]:
                    # This is a raw builtin function call
                    tokens.append(Token(caller, lex(unprocessed[1:right])))
                else:
                    tokens.append(Token("function", [caller, lex(unprocessed[1:right])]))
            else:
                tokens.append(Token("()", lex(unprocessed[1:right])))
            unprocessed = unprocessed[right+1:].strip()
            continue
        # Identify array literals and indexing operations
        if unprocessed.startswith("["):
            right = findMatching(unprocessed, left='[', right=']')
            if lastWasValue and tokens[-1].name == "name" and tokens[-1].data in dtypes.baseTypes:
                # This is an array creation operation
                dtype = tokens.pop(-1).data
                tokens.append(Token("array", [dtype, lex(unprocessed[1:right])]))
            elif lastWasValue:
                # This is an indexing operation
                tokens.append(Token("indexing", lex(unprocessed[1:right])))
            else:
                tokens.append(Token("literalArray", lex(unprocessed[1:right])))
            unprocessed = unprocessed[right+1:].strip()
            continue
        # Identify real literals
        match = re.match(r"\d*\.\d*", unprocessed)
        if match:
            tokens.append(Token("literal", [dtypes.Real, float(match.group())]))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify int literals
        match = re.match(r"\d+", unprocessed)
        if match:
            tokens.append(Token("literal", [dtypes.Int, int(match.group())]))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify bool literals
        match = re.match(r"(True|False)", unprocessed)
        if match:
            tokens.append(Token("literal", [dtypes.Bool, match.group().lower()]))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        # Identify names and types
        match = re.match(r"[a-zA-Z_]\w*", unprocessed)
        if match:
            tokens.append(Token("name", match.group()))
            unprocessed = unprocessed[len(match.group()):].strip()
            continue
        if unprocessed.startswith(")"):
            raise ValueError("ERROR: Unmatched ending parenthesis.")
        raise ValueError("ERROR: Cannot interpret code: {}".format(code))
    if debugLexer:
        sys.stderr.write("LEXER: "+code+" ===> "+str([t.name for t in tokens])+'\n')
    return tokens


def assertLastValue(tokens):
    '''Checks if the second most recent token was a value type and raises an error
    if that isn't the case.  Value types are things like 3 and (2343**x) that
    can be the left side of a binary operation, for example, and are listed in
    Token.valueTypes.'''
    if len(tokens) <= 1:
        raise ValueError("ERROR: Token '{}' cannot start a line, it needs a value to its left."
                         .format(tokens[0].name))
    if tokens[-2].name not in Token.valueTokens:
        raise ValueError("ERROR: token '{}' expected a value token to its left but found '{}'."
                         .format(tokens[-1].name, tokens[-2].name))
    return


def findMatching(s, start=0, left='(', right=')'):
    level = 0
    for i, c in enumerate(s[start:]):
        if c == left:
            level += 1
        elif c == right:
            level -= 1
            if level == 0:
                return i+start
    raise ValueError("ERROR: More {} than {}".format(left, right))
