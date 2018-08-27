import re
import sys
import dtypes


def lex(code, debugLexer=False):
    tokens = []
    unprocessed = code.strip()
    while unprocessed:
        # Identify comments
        if unprocessed[0] == '#':
            break
        # Check for errors
        if unprocessed.startswith(")"):
            raise ValueError("ERROR: Unmatched ending parenthesis.")
        # Search through tokens to find one that matches
        for TokenType in Token.__subclasses__():
            if TokenType.isMatch(unprocessed, tokens):
                unprocessed = TokenType.appendNew(tokens, unprocessed)
                break
        else:
            raise ValueError("ERROR: Cannot tokenize code from: {}".format(unprocessed))
    if debugLexer:
        sys.stderr.write("LEXER: "+code+" ===> "+str([t.name for t in tokens])+'\n')
    return tokens


class Token(object):
    precedence = ['print', '=', '+=', '-=', '/=', '//=', '*=', '**=', '%=', 'and', 'or',
                  'xor', '<=', '>=', '<', '>', '!=', '==',  '-', '+', '%', '*', '//', '/',
                  '**', 'unary +', 'unary -', 'indexing', 'function', 'array',
                  'literalArray', '()',  'literal', 'name', 'type']

    def getPrecedence(self):
        return Token.precedence.index(self.name)

    regex = None
    isValue = False
    startsLine = False
    followsValue = False
    endsWithColon = False
    unary = False

    def __init__(self, name, data=None):
        self.name = name
        self.data = data

    @classmethod
    def isMatch(cls, text, tokens):
        if cls.unary and tokens and tokens[-1].isValue:
            return False
        return re.match(cls.regex, text)

    @classmethod
    def appendNew(cls, tokens, sourceString):
        tokenString = re.match(cls.regex, sourceString).group()
        newToken = cls(tokenString)
        # Check for some syntax errors
        if cls.startsLine and len(tokens) != 0:
            raise ValueError("ERROR: Keyword {} must start the line.".format(tokenString))
        if cls.followsValue and len(tokens) == 0:
            raise ValueError("ERROR: Token '{}' cannot start a line, it needs a value to its left."
                             .format(newToken.name))
        if cls.followsValue and not tokens[-1].isValue:
            raise ValueError("ERROR: token '{}' expected a value token to its left but found '{}'."
                             .format(newToken.name, tokens[-1].name))
        if cls.endsWithColon:
            if sourceString[-1] != ':':
                raise ValueError('ERROR: Lines using {} must end in ":".'.format(newToken.name))
            sourceString = sourceString[:-1]
        # Add the new token to the list and pop the corresponding part of the source string
        tokens.append(newToken)
        sourceString = tokens[-1].extraInit(tokens, sourceString)
        return sourceString[len(tokenString):].strip()

    def extraInit(self, tokens, sourceString):
        return sourceString


class BlockStarterToken(Token):
    regex = r"(def|while|if|for)\b"
    startsLine = True
    endsWithColon = True


class PrintToken(Token):
    regex = r"Print\b"
    startsLine = True


class BasicToken(Token):
    regex = r'(,|\*\*?|%|//?|<=?|>=?|==)(?!\*?/?=)|in|and|or|xor'
    followsValue = True


class RealLiteralToken(Token):
    isValue = True
    regex = r"\d*\.\d*"

    def extraInit(self, tokens, sourceString):
        self.data = [dtypes.Real, float(self.name)]
        self.name = "literal"
        return sourceString


class IntLiteralToken(Token):
    isValue = True
    regex = r"\d+"

    def extraInit(self, tokens, sourceString):
        self.data = [dtypes.Int, int(self.name)]
        self.name = "literal"
        return sourceString


class BoolLiteralToken(Token):
    regex = r"(True|False)"
    isValue = True

    def extraInit(self, tokens, sourceString):
        self.data = [dtypes.Bool, self.name.lower()]
        self.name = "literal"
        return sourceString


class FunctionToken(Token):
    isValue = True
    regex = r"[a-zA-Z_]\w*\("

    @classmethod
    def appendNew(cls, tokens, sourceString):
        tokenString = re.match(cls.regex, sourceString).group()
        right = findMatching(sourceString, len(tokenString)-1)
        caller = tokenString[:-1]
        tokens.append(cls("function", [caller, lex(sourceString[len(tokenString):right])]))
        sourceString = sourceString[right+1:].strip()
        return sourceString


class ParensToken(Token):
    regex = r"\("
    isValue = True

    @classmethod
    def appendNew(cls, tokens, sourceString):
        right = findMatching(sourceString)
        tokens.append(cls('()', lex(sourceString[1:right])))
        sourceString = sourceString[right+1:].strip()
        return sourceString


class NameToken(Token):
    regex = r"[a-zA-Z_]\w*"
    isValue = True

    def extraInit(self, tokens, sourceString):
        self.data = self.name
        self.name = "name"
        return sourceString


class AssignmentToken(Token):
    regex = r'((\+|-|//?|\*\*?|%)?=)'

    @classmethod
    def appendNew(cls, tokens, sourceString):
        tokenString = re.match(cls.regex, sourceString).group()
        if len(tokens) == 1 and tokens[0].name == 'name':
            tokens.append(cls(tokenString, tokens.pop(0).data))
        elif len(tokens) > 1 and tokens[-1].name == "indexing":
            tokens.append(cls(tokenString, tokens[:]))
            del tokens[:-1]
        else:
            raise ValueError("ERROR: Assignment must be immeditely follow variable name.")
        return sourceString[len(tokenString):].strip()


class ArrayToken(Token):
    isValue = True
    regex = r"\["

    @classmethod
    def appendNew(cls, tokens, sourceString):
        # Identify array literals and indexing operations
        right = findMatching(sourceString, left='[', right=']')
        lastWasValue = tokens and tokens[-1].isValue
        if lastWasValue and tokens[-1].name == "name" and tokens[-1].data in dtypes.baseTypes:
            # This is an array creation operation
            dtype = tokens.pop(-1).data
            tokens.append(cls("array", [dtype, lex(sourceString[1:right])]))
        elif lastWasValue:
            # This is an indexing operation
            tokens.append(cls("indexing", lex(sourceString[1:right])))
        else:
            tokens.append(cls("literalArray", lex(sourceString[1:right])))
        return sourceString[right+1:].strip()


class UnaryPlusToken(Token):
    regex = r'\+'
    unary = True

    def extraInit(self, tokens, sourceString):
        # TODO: Remove once checking is no longer based on name
        self.name = 'unary +'
        return sourceString


class UnaryMinusToken(Token):
    regex = r'-'
    unary = True

    def extraInit(self, tokens, sourceString):
        # TODO: Remove once checking is no longer based on name
        self.name = 'unary -'
        return sourceString


class BinaryPlusToken(Token):
    regex = r'\+'


class BinaryMinusToken(Token):
    regex = r'-'


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
